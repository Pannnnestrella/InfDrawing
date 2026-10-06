"use client";

import { useEffect, useRef, useState } from "react";

import { AlertIcon, ImageIcon, RefreshIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import { pasteImageUrlToCanvas } from "@/lib/canvas-bridge";
import { openCanvasRequest } from "@/lib/canvas-request-store";
import {
  createLibrary,
  deleteItem,
  fetchLibraryArtifactUrl,
  listItems,
  listLibraries,
  patchItem,
  patchLibrary,
  recaptionItem,
  type AssetItem,
  type AssetLibrary,
} from "@/lib/library-api";
import {
  ASSET_TYPES,
  BACKGROUNDS,
  catalogLabel,
  GENRES,
  POSES,
  VIEWS,
  type CatalogMap,
} from "@/lib/library-catalog";
import {
  getLibraryDataRevision,
  subscribeLibraryData,
} from "@/library/library-panel-store";

function useLibraryThumb(artifactId: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!artifactId) return;
    let alive = true;
    fetchLibraryArtifactUrl(artifactId)
      .then((next) => {
        if (alive) setUrl(next);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [artifactId]);
  return url;
}

function AssetCard({
  item,
  selected,
  onSelect,
}: {
  item: AssetItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const thumb = useLibraryThumb(item.artifact_id);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`overflow-hidden rounded-xl border text-left transition-colors ${
        selected ? "border-accent bg-surface-2" : "border-line bg-surface-2/60 hover:border-accent/50"
      }`}
    >
      <div className="flex h-28 items-center justify-center bg-surface-3">
        {thumb ? (
          // Thumbnail of an owned library artifact; alt is the catalog title.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumb} alt={item.title} className="h-full w-full object-contain" />
        ) : (
          <Spinner size={16} />
        )}
      </div>
      <div className="px-2 py-1.5">
        <p className="truncate text-xs font-medium text-ink">{item.title}</p>
        <p className="truncate text-[10px] text-muted">
          {item.caption_status === "caption_failed"
            ? "标注失败"
            : [catalogLabel(ASSET_TYPES, item.asset_type), ...item.tags.slice(0, 2)]
                .filter(Boolean)
                .join(" · ")}
        </p>
      </div>
    </button>
  );
}

function splitList(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function CatalogSelect({
  label,
  value,
  catalog,
  onChange,
}: {
  label: string;
  value: string;
  catalog: CatalogMap;
  onChange: (code: string) => void;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted">{label}</span>
      <select
        className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">未填</option>
        {Object.entries(catalog).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function LibraryPanel() {
  const [libraries, setLibraries] = useState<AssetLibrary[]>([]);
  const [items, setItems] = useState<AssetItem[]>([]);
  const [libraryId, setLibraryId] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newLibraryName, setNewLibraryName] = useState("");
  const [newLibraryPurpose, setNewLibraryPurpose] = useState("");
  const [draftLibraryPurpose, setDraftLibraryPurpose] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftStyle, setDraftStyle] = useState("");
  const [draftType, setDraftType] = useState("");
  const [draftView, setDraftView] = useState("");
  const [draftGenre, setDraftGenre] = useState("");
  const [draftBackground, setDraftBackground] = useState("");
  const [draftPose, setDraftPose] = useState("");
  const [draftPalette, setDraftPalette] = useState("");
  const [draftMaterials, setDraftMaterials] = useState("");
  const [draftObjects, setDraftObjects] = useState("");
  const [draftKeywords, setDraftKeywords] = useState("");
  const [draftSource, setDraftSource] = useState("");
  const [draftCharacter, setDraftCharacter] = useState("");
  const [dataRevision, setDataRevision] = useState(getLibraryDataRevision);
  const jumpedRevisionRef = useRef(0);

  const selected = items.find((item) => item.id === selectedId) ?? null;

  function applyDrafts(item: AssetItem) {
    setDraftTitle(item.title);
    setDraftTags(item.tags.join("，"));
    setDraftKeywords((item.keywords ?? []).join("，"));
    setDraftDescription(item.description);
    setDraftStyle(item.style);
    setDraftSource(item.source_project ?? "");
    setDraftCharacter(item.character_name ?? "");
    setDraftType(item.asset_type ?? "");
    setDraftView(item.view ?? "");
    setDraftGenre(item.genre ?? "");
    setDraftBackground(item.background ?? "");
    setDraftPose(item.pose ?? "");
    setDraftPalette((item.palette ?? []).join("，"));
    setDraftMaterials((item.materials ?? []).join("，"));
    setDraftObjects(item.objects.join("，"));
  }

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(queryInput), 250);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => subscribeLibraryData(() => setDataRevision(getLibraryDataRevision())), []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        setError(null);
        const [libs, rows] = await Promise.all([
          listLibraries(),
          listItems(query, libraryId),
        ]);
        if (cancelled) return;
        setLibraries(libs);
        setItems(rows);
        if (rows[0] && dataRevision > jumpedRevisionRef.current) {
          // After ingest, jump to the newest item so success is visible.
          jumpedRevisionRef.current = dataRevision;
          const newest = rows[0];
          setSelectedId(newest.id);
          applyDrafts(newest);
        }
      } catch (exc: unknown) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "无法加载素材库");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [libraryId, query, dataRevision]);

  useEffect(() => {
    const current = libraries.find((library) => library.id === libraryId);
    setDraftLibraryPurpose(current?.purpose ?? "");
  }, [libraryId, libraries]);

  async function handleSave() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await patchItem(selected.id, {
        title: draftTitle,
        tags: splitList(draftTags),
        keywords: splitList(draftKeywords),
        objects: splitList(draftObjects),
        description: draftDescription,
        style: draftStyle,
        source_project: draftSource,
        character_name: draftCharacter,
        asset_type: draftType,
        view: draftView,
        genre: draftGenre,
        background: draftBackground,
        pose: draftPose,
        palette: splitList(draftPalette),
        materials: splitList(draftMaterials),
      });
      setItems((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      applyDrafts(updated);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handlePaste() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const url = await fetchLibraryArtifactUrl(selected.artifact_id);
      await pasteImageUrlToCanvas(url);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "贴回画布失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRecaption() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await recaptionItem(selected.id);
      setItems((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      applyDrafts(updated);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "重新标注失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await deleteItem(selected.id);
      setSelectedId(null);
      setItems((rows) => rows.filter((row) => row.id !== selected.id));
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePurpose() {
    if (!libraryId) return;
    const current = libraries.find((library) => library.id === libraryId);
    const next = draftLibraryPurpose.trim();
    if ((current?.purpose ?? "") === next) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await patchLibrary(libraryId, { purpose: next });
      setLibraries((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "保存用途失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateLibrary() {
    const name = newLibraryName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createLibrary(name, newLibraryPurpose.trim());
      setNewLibraryName("");
      setNewLibraryPurpose("");
      setLibraryId(created.id);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "新建库失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-1">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <select
          className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink"
          value={libraryId}
          onChange={(event) => setLibraryId(event.target.value)}
        >
          <option value="">全部库</option>
          {libraries.map((library) => (
            <option key={library.id} value={library.id}>
              {library.name}
            </option>
          ))}
        </select>
        {libraryId ? (
          <input
            className="w-40 rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs"
            placeholder="当前库用途"
            value={draftLibraryPurpose}
            disabled={busy}
            onChange={(event) => setDraftLibraryPurpose(event.target.value)}
            onBlur={() => void handleSavePurpose()}
          />
        ) : null}
        <input
          className="min-w-[160px] flex-1 rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink"
          placeholder="搜索类型 / 标签 / 来源 / 角色"
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
        />
        <input
          className="w-24 rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs"
          placeholder="新库名"
          value={newLibraryName}
          onChange={(event) => setNewLibraryName(event.target.value)}
        />
        <input
          className="w-36 rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs"
          placeholder="用途说明"
          value={newLibraryPurpose}
          onChange={(event) => setNewLibraryPurpose(event.target.value)}
        />
        <button
          type="button"
          className="rounded-lg border border-line px-2 py-1.5 text-xs hover:bg-surface-2"
          disabled={busy}
          onClick={() => void handleCreateLibrary()}
        >
          新建库
        </button>
        <button
          type="button"
          className="rounded-lg border border-line px-2 py-1.5 text-xs hover:bg-surface-2"
          onClick={() => openCanvasRequest("library-ingest", { pageX: 80, pageY: 80 })}
        >
          导入文件
        </button>
      </div>

      {error ? (
        <p className="flex items-start gap-1.5 px-3 py-2 text-[11px] text-warning">
          <AlertIcon size={13} className="mt-px shrink-0" />
          {error}
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-h-0 overflow-y-auto p-3">
          {items.length === 0 ? (
            <p className="flex items-center gap-2 text-xs text-muted">
              <ImageIcon size={14} />
              还没有素材。在画布上选中一张图，右键「加入素材库」。
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {items.map((item) => (
                <AssetCard
                  key={item.id}
                  item={item}
                  selected={item.id === selectedId}
                  onSelect={() => {
                    setSelectedId(item.id);
                    applyDrafts(item);
                  }}
                />
              ))}
            </div>
          )}
        </div>

        <aside className="min-h-0 overflow-y-auto border-l border-line p-3 text-xs">
          {selected ? (
            <div className="space-y-2">
              <label className="text-[11px] text-muted">标题</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftTitle}
                onChange={(event) => setDraftTitle(event.target.value)}
              />
              <div className="grid grid-cols-2 gap-2">
                <CatalogSelect
                  label="资产类型"
                  value={draftType}
                  catalog={ASSET_TYPES}
                  onChange={setDraftType}
                />
                <CatalogSelect
                  label="题材"
                  value={draftGenre}
                  catalog={GENRES}
                  onChange={setDraftGenre}
                />
                <CatalogSelect
                  label="视角"
                  value={draftView}
                  catalog={VIEWS}
                  onChange={setDraftView}
                />
                <CatalogSelect
                  label="姿态"
                  value={draftPose}
                  catalog={POSES}
                  onChange={setDraftPose}
                />
              </div>
              <CatalogSelect
                label="背景"
                value={draftBackground}
                catalog={BACKGROUNDS}
                onChange={setDraftBackground}
              />
              <label className="text-[11px] text-muted">主色（逗号分隔）</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftPalette}
                onChange={(event) => setDraftPalette(event.target.value)}
              />
              <label className="text-[11px] text-muted">材质（逗号分隔）</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftMaterials}
                onChange={(event) => setDraftMaterials(event.target.value)}
              />
              <label className="text-[11px] text-muted">物体（逗号分隔）</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftObjects}
                onChange={(event) => setDraftObjects(event.target.value)}
              />
              <label className="text-[11px] text-muted">标签（逗号分隔）</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftTags}
                onChange={(event) => setDraftTags(event.target.value)}
              />
              <label className="text-[11px] text-muted">关键词（逗号分隔）</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftKeywords}
                onChange={(event) => setDraftKeywords(event.target.value)}
              />
              <label className="text-[11px] text-muted">来源项目</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftSource}
                onChange={(event) => setDraftSource(event.target.value)}
              />
              <label className="text-[11px] text-muted">角色归属</label>
              <input
                className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftCharacter}
                onChange={(event) => setDraftCharacter(event.target.value)}
              />
              <label className="text-[11px] text-muted">内容描述</label>
              <textarea
                className="min-h-[64px] w-full resize-none rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftDescription}
                onChange={(event) => setDraftDescription(event.target.value)}
              />
              <label className="text-[11px] text-muted">风格</label>
              <textarea
                className="min-h-[56px] w-full resize-none rounded-lg border border-line bg-surface-2 px-2 py-1.5"
                value={draftStyle}
                onChange={(event) => setDraftStyle(event.target.value)}
              />
              {selected.caption_status === "caption_failed" ? (
                <p className="text-[11px] text-warning">{selected.caption_error}</p>
              ) : null}
              <div className="flex flex-wrap gap-1.5 pt-1">
                <button
                  type="button"
                  className="rounded-lg bg-accent px-2 py-1 text-white disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void handlePaste()}
                >
                  贴回画布
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-line px-2 py-1 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void handleSave()}
                >
                  保存修改
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void handleRecaption()}
                >
                  <RefreshIcon size={12} />
                  重新标注
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-line px-2 py-1 text-warning disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void handleDelete()}
                >
                  删除
                </button>
              </div>
            </div>
          ) : (
            <p className="text-muted">选中一张素材查看标注，并可改标签后搜索。</p>
          )}
        </aside>
      </div>
    </div>
  );
}
