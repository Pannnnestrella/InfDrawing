# Git 更新说明 — Lovart 功能线 Phase 0–4

> 生成日期：2025-06-11  
> 依据：`.planning/20250610_lovart_features.md`、`sidebar_chat_ux.md`、`text_edit_poc.md`、`进度.md`

---

## Commit Message（推荐）

```
feat: Lovart-style canvas AI features (Phase 0–4)

Deliver mask tool, capability detection, context-menu T2I, element
decompose, sidebar chat UX with mode chips, and text-edit POC (EasyOCR
+ inpaint + tldraw overlay). Unifies generate flows via intent_override
and canvas-bridge auto-placement.

Ref: .planning/20250610_lovart_features.md
```

---

## PR Title

```
feat: Lovart-style AI canvas — mask, decompose, sidebar chat, text edit (Phase 0–4)
```

---

## PR Body

```markdown
## Summary

Completes InfDrawing Phase 1 Lovart-style feature line (Phase 0–4), closing the interactive AI canvas demo loop for portfolio recording.

- **Phase 0** — Mask brush tool + generated images auto-placed on tldraw canvas via `canvas-bridge`
- **Phase 0.5** — `GET /system/capabilities` resource detection; frontend disables unavailable features with tooltips
- **Phase 1** — Right-click context menu AI image generation; local SD1.5 / cloud Flux routing stub
- **Phase 2** — Element decompose (`POST /generate/decompose`): rembg + SD1.5 inpaint → bg/fg dual layers on canvas
- **Phase 3** — Sidebar refactored to chat UX: `MessageList` + `ChatComposer` + mode chips `[生图][局部重绘][元素拆解][文字编辑]`; `intent_override` locks task routing
- **Phase 4** — Text edit POC: EasyOCR detect → inpaint erase → tldraw text overlay; `POST /vision/detect-text`, `POST /generate/text-edit`

**Cancelled:** standalone Tab inpaint UI (merged into sidebar inpaint).

## Backend

| Area | Changes |
|------|---------|
| `app/system/` | Capabilities detection (VRAM tier, ComfyUI/OCR availability) |
| `app/api/system.py` | Capabilities endpoint |
| `app/api/vision.py` | OCR text detection |
| `app/api/generate.py` | decompose, text-edit routes |
| `app/pipeline/` | decompose, text_detect, text_edit executors; txt2img router; image validation |
| `app/agent/` | `TEXT_EDIT`, `decompose` intents; intent_override handling |
| `tests/` | capabilities, decompose, text_edit, txt2img_router, image_validation |

## Frontend

| Area | Changes |
|------|---------|
| `agent-panel/` | ChatPanel refactor; ChatComposer, MessageList, ModeChips, TextRegionPicker |
| `canvas/` | MaskTool, AiContextMenu, DecomposeOverlay, PromptPopover |
| `lib/` | canvas-bridge, capabilities, ai-generate-store, decompose-store, generate-task |
| `components/` | CapabilityBanner, SidebarShell |

## Known limitations (demo scope)

- SD1.5 on 8GB VRAM — quality/speed constrained; Flux/SAM/AnyText2 reserved for cloud GPU
- Text edit uses OCR + inpaint + vector overlay, not AnyText2 font fusion
- Agent auto-intent (Stage 7) not included; button-selected mode only

## Test plan

- [ ] Start ComfyUI (`--lowvram`), backend, frontend per `进度.md`
- [ ] `GET /system/capabilities` returns correct tier and feature flags
- [ ] Sidebar: txt2img → image appears on canvas
- [ ] Select image + mask brush → inpaint via sidebar「局部重绘」
- [ ] Select image →「元素拆解」→ bg + fg layers on canvas
- [ ] Select image →「文字编辑」→ OCR list → replace one region → inpaint + text overlay
- [ ] Right-click AI generate still works
- [ ] `cd backend && .venv/Scripts/pytest tests/` passes

## Planning refs

- `.planning/20250610_lovart_features.md`
- `.planning/20250610_sidebar_chat_ux.md`
- `.planning/20250610_text_edit_poc.md`
```

---

## 上传命令

```powershell
cd D:\Desktop\Fan_Files\Codes\infDrawing

# 暂存（已排除 data/ 与 __pycache__）
git add .planning/20250610_*.md docs/git_update_20250611.md 进度.md
git add backend/app/agent/ backend/app/api/ backend/app/config.py backend/app/main.py
git add backend/app/pipeline/*.py backend/app/system/ backend/requirements.txt backend/tests/
git add frontend/src/ frontend/next.config.ts scripts/check_capabilities.py

# 提交
git commit -m "$(cat <<'EOF'
feat: Lovart-style canvas AI features (Phase 0–4)

Deliver mask tool, capability detection, context-menu T2I, element
decompose, sidebar chat UX with mode chips, and text-edit POC (EasyOCR
+ inpaint + tldraw overlay). Unifies generate flows via intent_override
and canvas-bridge auto-placement.

Ref: .planning/20250610_lovart_features.md
EOF
)"

# 推送
git push -u origin main
```

> Windows PowerShell 若无 heredoc，可直接使用 `-m "feat: ..."` 单行，或 `-m "title" -m "body..."` 多段 `-m`。

---

## 不应提交的文件

- `data/uploads/`, `data/outputs/` — 运行时二进制
- `frontend/.next/` — Next.js 构建产物
- `**/__pycache__/` — Python 字节码（建议后续加入根 `.gitignore`）
