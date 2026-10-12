# Controlled Multi-turn Edit

Controlled Multi-turn Edit lets a user revise one image over many turns while key elements (a character's face, a weapon, a prop) stay stable. It is an independent feature with its own router, scope and page:

| Item | Value |
|---|---|
| API prefix | `/api/v1/controlled-edit` |
| Required scope | `controlled_edit` |
| Capability flag | `features.controlled_edit` (enabled when `INFD_OPENAI_API_KEY` is set) |
| Frontend page | `/` (dock on the infinite canvas; `/studio` redirects home) |
| Backend package | `backend/app/controlled_edit/` |

The system records which entities must stay fixed and enforces this through prompt constraints,
reference-image anchoring and automatic VLM verification. Explicit local edits also use pixel
masks and deterministic crop/stitch blending. Every turn produces a node in a version tree,
so the user can roll back or branch.

Full-frame DashScope editors (Qwen Image 2.x / 3.0 and Wan 2.7) use the synchronous
multimodal-generation endpoint. Studio lists every edit-capable model from the catalog in the
image picker. The default full-frame model is `qwen-image-3.0-pro`.

## Concepts

**Scene entities.** When a session is created, a dedicated grounding model (Qwen-VL via DashScope when `INFD_DASHSCOPE_API_KEY` or `INFD_ALIBABA_API_KEY` is set; otherwise `INFD_CEDIT_VISION_MODEL`) parses the image into an entity tree (for example `character`, `character.face`, `character.sword`, `environment.sky`). Each entity has a dotted snake_case id, a description and a bounding box on a normalized 0–1 grid. The parser always lists `face` and `hair` for characters, because identity drift is the most visible failure. Intent parsing and verification stay on the OpenAI vision model.

**Manual box correction.** The user can drag and resize a box on `/studio`. Saving writes `bbox_source: "manual"`. On the next re-parse, only locked entities keep a manual box; other entities take the newly parsed boxes. Changing the box of a locked entity recrops its lock-time anchor.

**Region-guided edits.** Clicking an entity sets the turn target (`target_entity_ids`). Small
`character.*` parts with a box use the **auto-local** path: by default Wan 2.7
(`INFD_CEDIT_AUTO_LOCAL_MODEL`, typically `wan2.7-image-pro`) with `bbox_list` built from the
entity boxes (up to two largest targets). Set `INFD_CEDIT_AUTO_LOCAL_ENGINE=wanx21_mask` to
fall back to legacy Wanx 2.1 binary-mask inpaint. Explicit Studio Mask edits (SAM / freehand)
still use Legacy `wanx2.1-imageedit` with `placement=crop|fullframe`. Background / whole-subject
/ large boxes always edit the **full current frame** with the picker model (Qwen / Wan 2.7 /
OpenAI), plus optional lock paste. Locked-entity anchor crops are attached as identity
references on the full-frame path.

**Entity status.** Each entity carries one of three states, stored per version node:

| Status | Prompt effect | Reference anchor | Verification |
|---|---|---|---|
| `locked` | Listed under "Preserve exactly", tied to a reference image when an anchor exists | Crop taken only for the entity the user clicked | Score below `INFD_CEDIT_PRESERVE_THRESHOLD` fails the turn |
| `approved` | Listed under "Keep unchanged unless asked" | None | Score below threshold only adds a warning |
| `editable` | No extra constraint | None | Not checked |

Locking a parent also locks every descendant (cascade). Only the clicked node gets an anchor crop; children show as locked without their own reference image and cannot be unlocked until the parent is unlocked. Unlocking the parent clears the lock on all descendants.

The preserve lists are generated deterministically from entity states; the language model never decides what to protect. An instruction that targets a locked entity (or a child of a locked entity) is rejected with HTTP 409 `lock_conflict`, and the UI offers to unlock and retry.

**Lock paste (optional).** Hard pixel paste-back of locked boxes is off by default (`INFD_CEDIT_LOCK_PASTE=false`). When enabled, only locked entities that have an anchor crop are pasted from the parent frame onto the result.

**Version tree.** Each version node stores the image artifact, the instruction, the parsed intent, the compiled prompt, the reference artifacts, an entity snapshot, the verification result, the attempt count and warnings. Editing from any node creates a child; checking out a node moves the session's current pointer without deleting history.

## Turn pipeline

1. **Intent parsing** (synchronous, inside `POST /turns`): the LLM maps the instruction and the entity table to an operation (`add`, `remove`, `replace`, `restyle`, `recolor`, `other`), target entity ids and a change description. Lock conflicts return immediately.
2. **Background run**: a pending child version is created and the turn continues as an in-process task. The frontend polls the session tree every 2 s and shows the progress step (`preparing`, `generating`, `verifying`, `parsing`).
3. **Sizing**: the source is letterboxed to the closest supported size (`1024x1024`, `1536x1024`, `1024x1536`) and restored to the original frame afterwards. When the parent has meaningful alpha (or the instruction asks for cutout / transparency) and the editor is Qwen, pad/restore keep RGBA; Wan / Wanx paths flatten to RGB for the API and reattach parent alpha outside the edit support afterward.
4. **Prompt compilation**: each turn may send `prompt_style` (`preserve` / `target_only`); otherwise `INFD_CEDIT_PROMPT_STYLE` is used. `preserve` includes the change, target boxes, locked/approved keep lists, framing clauses, and reference-image numbers. `target_only` describes only the change and target boxes, plus short pointers for attached identity reference crops. DashScope numbering treats the current image as last.
5. **Generation**: each turn may send `image_provider` (`dashscope` / `openai`); otherwise `INFD_CEDIT_IMAGE_PROVIDER` is used. The editor always receives the full current image plus optional lock-anchor reference crops. When `INFD_CEDIT_LOCK_PASTE` is on, anchored locked boxes are copied from the parent after generation. Transport errors are retried twice with backoff.
6. **Verification**: a subject-box framing check runs first; drift above the configured thresholds fails the attempt. Otherwise a VLM compares the before and after images, plus the anchor crops. It reports whether the change was applied, a composition score, and for each protected entity a score against the parent image and a `reference_score` against its anchor crop. The effective score of a locked entity is the lower of the two. The turn fails when the change is missing, a locked entity falls below the preserve threshold, or the composition score falls below `INFD_CEDIT_COMPOSITION_THRESHOLD`.
7. **Retry**: on failure the turn is regenerated up to `INFD_CEDIT_MAX_RETRIES` times with the failure reasons appended to the prompt. If the last attempt still fails, the image is saved and the node is marked with a warning, so the user can decide whether to keep it or roll back.
8. **Incremental re-parse**: the new image is re-parsed with the previous entity table as context. Entities keep their ids and statuses; a locked entity missing from the new parse is kept and flagged with a warning.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Multipart upload (`image`, optional `title`); parses the scene and returns the tree (201) |
| `GET` | `/sessions` | List the caller's sessions |
| `GET` | `/sessions/{session_id}` | Session with all versions |
| `POST` | `/sessions/{session_id}/turns` | `{"parent_version_id", "instruction", "target_entity_ids"?, "prompt_style"?, "image_provider"?}`; returns the pending version (202) or 409 `lock_conflict` / editor unavailable |
| `POST` | `/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/status` | Set `locked` / `approved` / `editable`; locking stores an anchor crop |
| `PUT` | `/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/bbox` | Save a manual box `{x, y, w, h}` in normalized image units |
| `POST` | `/sessions/{session_id}/checkout` | Move the current pointer to a version |
| `DELETE` | `/sessions/{session_id}/versions/{version_id}` | Delete a version and all descendants (not the root; not while pending/running). Cursor moves to the parent when needed. Image artifacts on disk are kept. |
| `GET` | `/artifacts/{artifact_id}` | Image bytes, restricted to the session owner |
| `POST` | `/workflows` | Create a reusable edit workflow DAG |
| `GET` | `/workflows` | List owned workflow templates |
| `GET` / `PUT` / `DELETE` | `/workflows/{workflow_id}` | Read, update, or delete a template |
| `POST` | `/sessions/{session_id}/export-workflow` | Export a connected version subgraph into a saved workflow |
| `POST` | `/workflows/{workflow_id}/runs` | Upload an image and execute the workflow (202) |
| `GET` | `/workflow-runs/{run_id}` | Poll one run |
| `POST` | `/workflow-runs/{run_id}/resume` | Resume a run paused on a `manual` condition |

Errors use the standard error envelope. Upstream model failures map to 502, missing resources to 404, and edits from a version that is still running to 409.

## Edit workflow graphs

Workflow **templates** are reusable DAGs. A **run** materializes a new `EditSession` version tree. The live Studio tree stays the execution history; the editor at `/workflows` edits templates with `@xyflow/react`.

| Node type | Role |
|---|---|
| `input` | Entry image (exactly one per template) |
| `edit` | One controlled-edit turn (`instruction`, `lock_roles`, `target_roles`, model options) |
| `condition` | Gate: `target_applied`, `locked_score`, `entity_role_exists`, or `manual` (pauses the run) |
| `merge` | Fan-in: `multi_ref` (primary + other branches as references) or `select_best` |
| `output` | Terminal marker (one or more) |

Entity binding uses **roles** (leaf id / name such as `face`), not absolute entity ids from the source session. Merge-produced versions keep a single `parent_id` for tree layout and record every source in `input_version_ids`.

Studio: Ctrl/Cmd-click nodes on the version tree, then **存为工作流**, or export the whole tree. Open `/workflows` to edit, save, and run against a new image.

Templates persist under `data/cedit/workflows.json` in memory mode (table `edit_workflows` when using Postgres).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `INFD_CEDIT_IMAGE_PROVIDER` | `dashscope` | Image editor: `dashscope` or `openai` |
| `INFD_CEDIT_IMAGE_MODEL` | `qwen-image-3.0-pro` | Default full-frame DashScope edit model |
| `INFD_CEDIT_AUTO_LOCAL_ENGINE` | `wan27_bbox` | Auto small-object path: `wan27_bbox` or `wanx21_mask` |
| `INFD_CEDIT_AUTO_LOCAL_MODEL` | `wan2.7-image-pro` | Model for `wan27_bbox` auto-local turns |
| `INFD_DASHSCOPE_EDIT_MODEL` | `wanx2.1-imageedit` | Legacy binary-mask inpaint model (explicit Mask only) |
| `INFD_CEDIT_VISION_MODEL` | `gpt-4o` | Vision model for intent parsing and verification |
| `INFD_CEDIT_SCENE_PROVIDER` | `dashscope` | Scene-parsing provider; set to `openai` to reuse the vision model |
| `INFD_CEDIT_SCENE_MODEL` | `qwen3-vl-plus` | Dedicated grounding model (DashScope compatible mode) |
| `INFD_CEDIT_SCENE_BASE_URL` | DashScope compatible-mode `/v1` | OpenAI-compatible chat completions endpoint |
| `INFD_CEDIT_SCENE_BBOX_FORMAT` | `xyxy_1000` | How `box_2d` is read: `xyxy_1000`, `yxyx_1000`, or `xyxy_pixel` |
| `INFD_CEDIT_VISION_TIMEOUT_SECONDS` | `90` | Timeout per vision call |
| `INFD_CEDIT_PRESERVE_THRESHOLD` | `0.7` | Minimum score for locked entities |
| `INFD_CEDIT_COMPOSITION_THRESHOLD` | `0.75` | Minimum composition score |
| `INFD_CEDIT_MAX_RETRIES` | `1` | Automatic regenerations after a failed verification |
| `INFD_CEDIT_MAX_REFERENCE_IMAGES` | `4` | Maximum anchor crops attached per turn |
| `INFD_CEDIT_INPUT_FIDELITY` | `high` | `input_fidelity` sent to the OpenAI image model |
| `INFD_CEDIT_MAX_ENTITIES` | `30` | Upper bound on parsed entities |
| `INFD_CEDIT_PROMPT_STYLE` | `preserve` | Default edit prompt style when the Studio picker does not override: `preserve` or `target_only` |
| `INFD_CEDIT_LOCK_PASTE` | `false` | When true, paste anchored locked boxes from the parent onto each result |
| `INFD_CEDIT_LOCK_FEATHER` | `0.12` | Feather width when pasting locked or cropped boxes |
| `INFD_CEDIT_SUBJECT_SHIFT_THRESHOLD` | `0.08` | Subject-center shift that fails framing before VLM review |
| `INFD_CEDIT_SUBJECT_AREA_THRESHOLD` | `0.15` | Subject-area change that fails framing before VLM review |
| `INFD_CEDIT_WORKFLOW_CONCURRENCY` | `2` | Max parallel edit nodes inside one workflow run |

Sessions and versions are stored in `edit_sessions` / `edit_versions` (migration `0002_controlled_edit`) when a database is configured. In local `memory` mode they are written to `data/cedit/sessions.json` after every create or save, and artifact metadata is written to `data/cedit/artifacts.json`, so a backend restart keeps the version tree.

## End-to-end check

`scripts/cedit_e2e.py` creates a session against a running backend, locks the face, sword and shield, runs three turns (witch hat, Halloween night background, glowing pumpkin) and writes images, scores and the configuration to `data/logs/{YYYYMMDD}_controlled_edit_e2e/`:

```bash
backend/.venv/Scripts/python scripts/cedit_e2e.py --image path/to/source.png --out data/logs/<run_dir>
```

## Transparency (RGBA)

Session upload already stores PNG with alpha when present. Child versions keep an RGBA chain when the parent has transparency.

| Path | Send to model | Output alpha |
|---|---|---|
| Qwen Image (2.1 / 3.0 full-frame) | Prefer PNG with alpha when parent is transparent or the instruction mentions cutout / 透明 / 抠图 / 去背 | May emit transparent PNG; Studio prompts allow alpha in that case |
| Wan 2.7 (full-frame or auto-local bbox) | Flatten onto a neutral opaque background (API has no alpha) | Outside edit support (bbox / full frame): reattach parent alpha; inside support: keep parent alpha unless the model returned alpha |
| Wanx 2.1 Legacy mask (crop or fullframe) | Flatten RGB + binary mask | Crop/stitch preserves outside-support pixels including alpha; fullframe reattaches parent alpha outside the mask |

Forced cutout-to-transparent is not the default for every model. Explicit “抠透明素材” intent is honored on Qwen (and SAM→Qwen experiment prompts via `qwen_mask_edit_prompt`). Studio Mask + Wanx remains Legacy RGB inpaint; use Qwen full-frame for new transparency.

## Known limitations

- The VLM verifier is lenient: in the 2026-10-05 runs it scored composition 1.0 on a turn with a visible push-in, and it does not detect gradual brushwork degradation across turns. Framing drift now fails those zoom-in cases before the VLM call.
- Grounding uses Qwen-VL (`qwen3-vl-plus` by default). Boxes are tight enough for face, sword and shield on the 2026-10-05 comparison set; group boxes (character, environment) still cover extra background. A comparison script lives at `scripts/cedit_grounding_compare.py`.
- Each turn re-encodes the full image, so texture quality can degrade over long chains. Branching from an earlier node is the recovery path.
- Turns run inside the API process; a restart interrupts running turns. Session trees and artifact metadata persist in `data/cedit/` in local `memory` mode.
# Local mask crop and stitch

Explicit local edits accept a mask bound to the selected parent version and its image hash.
The Studio mask panel supports freehand lasso, polygon, brush/erase, undo/redo, SAM 2.1
box/point prompts, candidate selection, and an offline crop preview. Confirm the mask before
submitting an edit. Switching versions clears the active selection.

`InpaintOptions.placement` selects how an **explicit** mask is sent to Legacy Wanx 2.1:

- `crop` (default): threshold / dilate / feather, expand context onto a conservative 1024
  square working canvas, send crop + binary mask, then `inpaint_stitch` so pixels outside
  the blending-mask support stay byte-identical to the parent PNG.
- `fullframe`: prepare the same source-space hard mask and send the **full parent image**
  plus that mask. There is no stitch step; preservation outside the mask relies on Wanx.
  Context-expansion options do not change the payload size.

Automatic small-object turns (no explicit mask) default to Wan 2.7 + `bbox_list` instead of a
binary mask. SAM 2.1 is optional and loaded lazily. Wan 2.7 has no mask field; Qwen Image
models remain full-frame instruction editors.

Paid smoke probes for the upgraded defaults:
`backend/.venv/Scripts/python ../scripts/cedit_model_upgrade_probe.py --generate`
(writes `data/logs/20261012_cedit_model_upgrade_probe/`).

Run `backend/.venv/Scripts/python scripts/cedit_crop_stitch_compare.py` from the repository
root to prepare a real SAM mask and review page without cloud generation. The page is at
`/inpaint-comparison/index.html` on the frontend. Only use `--generate` after cost approval;
the script records an attempt before calling each model and never retries it automatically.
Logs for that shield experiment live under `data/logs/20261012_local_inpaint_crop_stitch/`.

For a four-method two-turn comparison (weapon / face; Qwen 2.1 full-frame, SAM crop Wanx,
SAM full-frame Wanx, entity-rect Wanx), run
`backend/.venv/Scripts/python ../scripts/cedit_method_compare.py` then `--generate`.
Merged grids are written to `data/logs/20261012_method_compare_weapon_face/compare_*.png`.
