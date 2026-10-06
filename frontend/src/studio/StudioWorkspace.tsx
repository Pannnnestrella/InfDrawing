"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiKeyControl } from "@/components/ApiKeyControl";
import { AlertIcon } from "@/components/icons";
import { SplitPane } from "@/components/SplitPane";
import { fetchCapabilities, featureReason, type CapabilitiesResponse } from "@/lib/capabilities";
import { exportSelectedImageFile, pasteImageUrlToCanvas } from "@/lib/canvas-bridge";
import {
  ControlledEditApiError,
  checkoutVersion,
  createSession,
  deleteVersion,
  fetchArtifactBlobUrl,
  getSessionTree,
  isVersionBusy,
  listSessions,
  submitTurn,
  updateEntityBBox,
  updateEntityStatus,
  type BBox,
  type EditSession,
  type EditVersion,
  type EntityStatus,
  type LockConflictEntity,
  type SessionTree,
} from "@/lib/controlled-edit-api";

import { EditComposer } from "./EditComposer";
import { EntityPanel } from "./EntityPanel";
import {
  loadImageProvider,
  loadPromptStyle,
  parseImageOptions,
  saveImageProvider,
  savePromptStyle,
  type ImageProviderOption,
  type PromptStyleOption,
} from "./studio-turn-options";
import { SPLIT_DEFAULTS, SPLIT_MIN, useSplitSize } from "./studio-split";
import { UploadPanel } from "./UploadPanel";
import { VersionDetails } from "./VersionDetails";
import { VersionTree } from "./VersionTree";
import { VersionViewer } from "./VersionViewer";

const POLL_MS = 2000;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function replaceVersion(tree: SessionTree, version: EditVersion): SessionTree {
  return { ...tree, versions: tree.versions.map((v) => (v.id === version.id ? version : v)) };
}

export function StudioWorkspace({ layout = "float" }: { layout?: "page" | "float" }) {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [sessions, setSessions] = useState<EditSession[]>([]);
  const [tree, setTree] = useState<SessionTree | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pendingEntityId, setPendingEntityId] = useState<string | null>(null);
  const [hoveredEntityId, setHoveredEntityId] = useState<string | null>(null);
  const [boxEdit, setBoxEdit] = useState<{ versionId: string; entityId: string } | null>(null);
  const [savingBBox, setSavingBBox] = useState(false);
  const [selectedTargetIds, setSelectedTargetIds] = useState<string[]>([]);
  const [promptStyle, setPromptStyle] = useState<PromptStyleOption>("preserve");
  const [imageProvider, setImageProvider] = useState<ImageProviderOption>("dashscope");
  const [importing, setImporting] = useState(false);
  const [asideWidth, setAsideWidth] = useSplitSize(
    "aside",
    SPLIT_DEFAULTS.aside,
    SPLIT_MIN.aside,
  );
  const [treeHeight, setTreeHeight] = useSplitSize("tree", SPLIT_DEFAULTS.tree, SPLIT_MIN.tree);
  const [entityHeight, setEntityHeight] = useSplitSize(
    "entities",
    SPLIT_DEFAULTS.entities,
    SPLIT_MIN.entities,
  );
  const [detailsHeight, setDetailsHeight] = useSplitSize(
    "details",
    SPLIT_DEFAULTS.details,
    SPLIT_MIN.details,
  );
  const [conflict, setConflict] = useState<{
    instruction: string;
    entities: LockConflictEntity[];
  } | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    let alive = true;
    fetchCapabilities()
      .then((caps) => {
        if (!alive) return;
        setCapabilities(caps);
        const models = caps.features.controlled_edit?.models ?? {};
        const options = parseImageOptions(models.image_options);
        const style =
          models.prompt_style === "target_only" || models.prompt_style === "preserve"
            ? models.prompt_style
            : "preserve";
        const provider =
          models.image_provider === "openai" || models.image_provider === "dashscope"
            ? models.image_provider
            : "dashscope";
        setPromptStyle(loadPromptStyle(style));
        setImageProvider(loadImageProvider(options, provider));
      })
      .catch(() => undefined);
    listSessions()
      .then((items) => alive && setSessions(items))
      .catch((err: unknown) => alive && setError(errorMessage(err)));
    return () => {
      alive = false;
    };
  }, []);

  const sessionId = tree?.session.id ?? null;
  const hasBusyVersion = tree?.versions.some(isVersionBusy) ?? false;

  useEffect(() => {
    if (!sessionId || !hasBusyVersion) return;
    const timer = window.setInterval(() => {
      getSessionTree(sessionId)
        .then(setTree)
        .catch((err: unknown) => setError(errorMessage(err)));
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [sessionId, hasBusyVersion]);

  const current = useMemo(
    () => tree?.versions.find((v) => v.id === tree.session.current_version_id) ?? null,
    [tree],
  );
  const parent = useMemo(
    () => (current?.parent_id ? (tree?.versions.find((v) => v.id === current.parent_id) ?? null) : null),
    [tree, current],
  );
  const entityNames = useMemo(
    () => Object.fromEntries((parent ?? current)?.entities.map((e) => [e.id, e.name]) ?? []),
    [parent, current],
  );
  const highlightedEntity = current?.entities.find((e) => e.id === hoveredEntityId) ?? null;
  const editingEntity =
    boxEdit && current && boxEdit.versionId === current.id
      ? (current.entities.find((e) => e.id === boxEdit.entityId) ?? null)
      : null;
  const featureDisabledReason = featureReason(capabilities, "controlled_edit");
  const currentReady = current?.status === "succeeded";
  const canDeleteCurrent = Boolean(
    current?.parent_id && current && !isVersionBusy(current) && !deleting,
  );
  const imageOptions = useMemo(
    () => parseImageOptions(capabilities?.features.controlled_edit?.models?.image_options),
    [capabilities],
  );

  const handleCreate = async (file: File, title: string) => {
    setCreating(true);
    setError(null);
    try {
      setTree(await createSession(file, title));
      void refreshSessions();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const handleCreateFromCanvas = async () => {
    setCreating(true);
    setError(null);
    try {
      const file = await exportSelectedImageFile();
      if (!file) {
        setError("请先在画布上选中一张图片");
        return;
      }
      setTree(await createSession(file, file.name.replace(/\.[^.]+$/, "")));
      void refreshSessions();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const handleOpen = async (id: string) => {
    setError(null);
    try {
      setTree(await getSessionTree(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const handleSelect = async (versionId: string) => {
    if (!tree || versionId === tree.session.current_version_id) return;
    setConflict(null);
    try {
      const session = await checkoutVersion(tree.session.id, versionId);
      setTree((prev) => (prev ? { ...prev, session } : prev));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const handleDeleteCurrent = async () => {
    if (!tree || !current?.parent_id || isVersionBusy(current)) return;
    const ordinal =
      [...tree.versions]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .findIndex((version) => version.id === current.id) + 1;
    const childIds = new Map<string, string[]>();
    for (const version of tree.versions) {
      if (!version.parent_id) continue;
      childIds.set(version.parent_id, [...(childIds.get(version.parent_id) ?? []), version.id]);
    }
    let descendantCount = 0;
    const stack = [...(childIds.get(current.id) ?? [])];
    while (stack.length > 0) {
      const id = stack.pop()!;
      descendantCount += 1;
      stack.push(...(childIds.get(id) ?? []));
    }
    const message =
      descendantCount > 0
        ? `删除 v${ordinal} 及其全部后续分支（共 ${descendantCount + 1} 个节点）？此操作不可撤销。`
        : `删除 v${ordinal}？此操作不可撤销。`;
    if (!window.confirm(message)) return;
    setDeleting(true);
    setError(null);
    setConflict(null);
    try {
      setTree(await deleteVersion(tree.session.id, current.id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  };

  const handleStatusChange = async (entityId: string, status: EntityStatus) => {
    if (!tree || !current) return;
    setPendingEntityId(entityId);
    try {
      const updated = await updateEntityStatus(tree.session.id, current.id, entityId, status);
      setTree((prev) => (prev ? replaceVersion(prev, updated) : prev));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPendingEntityId(null);
    }
  };

  const handleSaveBBox = async (bbox: BBox) => {
    if (!tree || !current || !editingEntity) return;
    setSavingBBox(true);
    try {
      const updated = await updateEntityBBox(tree.session.id, current.id, editingEntity.id, bbox);
      setTree((prev) => (prev ? replaceVersion(prev, updated) : prev));
      setBoxEdit(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingBBox(false);
    }
  };

  const handleSubmit = async (instruction: string): Promise<boolean> => {
    if (!tree || !current) return false;
    setSubmitting(true);
    setError(null);
    setConflict(null);
    try {
      await submitTurn(tree.session.id, current.id, instruction, selectedTargetIds, {
        promptStyle,
        imageProvider,
      });
      setSelectedTargetIds([]);
      setTree(await getSessionTree(tree.session.id));
      return true;
    } catch (err) {
      if (err instanceof ControlledEditApiError && err.code === "lock_conflict") {
        setConflict({ instruction, entities: err.conflictEntities });
      } else {
        setError(errorMessage(err));
      }
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnlockAndRetry = async () => {
    if (!tree || !current || !conflict) return;
    const { instruction, entities } = conflict;
    setSubmitting(true);
    try {
      for (const entity of entities) {
        await updateEntityStatus(tree.session.id, current.id, entity.id, "editable");
      }
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    await handleSubmit(instruction);
  };

  const handleImportToCanvas = async () => {
    if (!current?.image_artifact_id) {
      setError("当前版本没有可导入的图片");
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const url = await fetchArtifactBlobUrl(current.image_artifact_id);
      const pasted = await pasteImageUrlToCanvas(url);
      if (!pasted) {
        setError("导入失败：画布未就绪");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setImporting(false);
    }
  };

  const floating = layout === "float";
  const canImport = Boolean(currentReady && current?.image_artifact_id);

  return (
    <div
      className={`flex flex-col overflow-hidden bg-surface-0 text-ink ${
        floating ? "h-full w-full" : "h-screen w-screen"
      }`}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          {floating ? null : (
            <Link href="/" className="text-xs text-muted hover:text-ink">
              ← 画布
            </Link>
          )}
          <h1 className="text-sm font-semibold tracking-wide">多轮可控编辑</h1>
          {tree ? (
            <span className="truncate text-xs text-muted">/ {tree.session.title}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {tree ? (
            <button
              type="button"
              onClick={() => {
                setTree(null);
                setConflict(null);
                void refreshSessions();
              }}
              className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-ink"
            >
              新建 / 打开会话
            </button>
          ) : null}
          {tree && current ? (
            <button
              type="button"
              disabled={!canImport || importing}
              onClick={() => void handleImportToCanvas()}
              className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              {importing ? "导入中…" : "导入画布"}
            </button>
          ) : null}
          {floating ? null : <ApiKeyControl />}
        </div>
      </header>

      {featureDisabledReason || error ? (
        <div className="flex shrink-0 items-center gap-2 border-b border-line bg-danger/10 px-4 py-2 text-xs text-danger">
          <AlertIcon size={14} />
          <span className="flex-1">{error ?? featureDisabledReason}</span>
          {error ? (
            <button type="button" onClick={() => setError(null)} className="text-muted hover:text-ink">
              关闭
            </button>
          ) : null}
        </div>
      ) : null}

      {!tree || !current ? (
        <main className="panel-scroll flex-1 overflow-y-auto px-4">
          <UploadPanel
            sessions={sessions}
            creating={creating}
            disabled={Boolean(featureDisabledReason)}
            compact={floating}
            onCreate={(file, title) => void handleCreate(file, title)}
            onCreateFromCanvas={() => void handleCreateFromCanvas()}
            onOpen={(id) => void handleOpen(id)}
          />
        </main>
      ) : (
        <main className="min-h-0 flex-1">
          <SplitPane
            axis="x"
            secondarySize={asideWidth}
            minSecondary={SPLIT_MIN.aside}
            minPrimary={SPLIT_MIN.preview}
            onSecondarySizeChange={setAsideWidth}
            label="调整右侧栏宽度"
          >
            <SplitPane
              axis="y"
              secondarySize={treeHeight}
              minSecondary={SPLIT_MIN.tree}
              minPrimary={SPLIT_MIN.preview}
              onSecondarySizeChange={setTreeHeight}
              label="调整修改树高度"
            >
              <div className="h-full min-h-0 p-3">
                <VersionViewer
                  version={current}
                  parent={parent}
                  highlightedEntity={highlightedEntity}
                  editingEntity={editingEntity}
                  savingBBox={savingBBox}
                  onSaveBBox={(bbox) => void handleSaveBBox(bbox)}
                  onCancelEdit={() => setBoxEdit(null)}
                />
              </div>
              <section className="flex h-full min-h-0 flex-col bg-surface-1 p-2">
                <header className="mb-1 flex items-center justify-between gap-2 px-1">
                  <div className="min-w-0">
                    <h2 className="text-xs font-semibold tracking-wide">修改树</h2>
                    <p className="truncate text-[10px] text-faint">
                      点击节点切换预览；从旧节点继续编辑会形成分支
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={!canDeleteCurrent}
                    title={
                      !current.parent_id
                        ? "原图根节点不能删除"
                        : isVersionBusy(current)
                          ? "生成中的版本不能删除"
                          : "删除当前节点及其后续分支"
                    }
                    onClick={() => void handleDeleteCurrent()}
                    className="shrink-0 rounded-md border border-danger/40 px-2 py-1 text-[10px] text-danger transition-colors hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {deleting ? "删除中…" : "删除当前节点"}
                  </button>
                </header>
                <div className="min-h-0 flex-1">
                  <VersionTree
                    versions={tree.versions}
                    currentVersionId={tree.session.current_version_id}
                    disabled={deleting}
                    onSelect={(id) => void handleSelect(id)}
                  />
                </div>
              </section>
            </SplitPane>
            <aside className="flex h-full min-h-0 flex-col border-l border-line">
              <SplitPane
                axis="y"
                secondarySize={detailsHeight}
                minSecondary={SPLIT_MIN.details}
                minPrimary={SPLIT_MIN.composer}
                onSecondarySizeChange={setDetailsHeight}
                label="调整本轮详情高度"
              >
                <SplitPane
                  axis="y"
                  secondarySize={entityHeight}
                  minSecondary={SPLIT_MIN.entities}
                  minPrimary={SPLIT_MIN.composer}
                  onSecondarySizeChange={setEntityHeight}
                  label="调整实体列表高度"
                >
                  <div className="panel-scroll h-full min-h-0 overflow-y-auto p-3">
                    <EditComposer
                      disabled={!currentReady || Boolean(featureDisabledReason)}
                      disabledReason={
                        currentReady
                          ? null
                          : current.status === "failed"
                            ? "该版本生成失败，请切换到其他节点"
                            : "当前版本生成中…"
                      }
                      submitting={submitting}
                      conflict={conflict}
                      selectedTargets={current.entities.filter((e) =>
                        selectedTargetIds.includes(e.id),
                      )}
                      promptStyle={promptStyle}
                      imageProvider={imageProvider}
                      imageOptions={imageOptions}
                      onPromptStyleChange={(style) => {
                        setPromptStyle(style);
                        savePromptStyle(style);
                      }}
                      onImageProviderChange={(provider) => {
                        setImageProvider(provider);
                        saveImageProvider(provider);
                      }}
                      onSubmit={handleSubmit}
                      onUnlockAndRetry={() => void handleUnlockAndRetry()}
                      onDismissConflict={() => setConflict(null)}
                    />
                  </div>
                  <div className="h-full min-h-0 overflow-hidden px-3 pb-3">
                    <EntityPanel
                      entities={current.entities}
                      disabled={!currentReady}
                      pendingEntityId={pendingEntityId}
                      editingEntityId={editingEntity?.id ?? null}
                      onStatusChange={(id, status) => void handleStatusChange(id, status)}
                      onHover={setHoveredEntityId}
                      selectedTargetIds={selectedTargetIds}
                      onToggleTarget={(id) =>
                        setSelectedTargetIds((prev) =>
                          prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
                        )
                      }
                      onEditBox={(id) =>
                        setBoxEdit((prev) =>
                          prev?.versionId === current.id && prev.entityId === id
                            ? null
                            : { versionId: current.id, entityId: id },
                        )
                      }
                    />
                  </div>
                </SplitPane>
                <div className="panel-scroll h-full min-h-0 overflow-y-auto border-t border-line p-3">
                  <VersionDetails version={current} entityNames={entityNames} />
                </div>
              </SplitPane>
            </aside>
          </SplitPane>
        </main>
      )}
    </div>
  );
}
