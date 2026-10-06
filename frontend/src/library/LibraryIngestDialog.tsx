"use client";

import { useEffect, useRef, useState } from "react";

import { AlertIcon, ImageIcon } from "@/components/icons";
import { Spinner } from "@/components/Spinner";
import {
  exportSelectedImageFiles,
  getLibraryExportHint,
} from "@/lib/canvas-bridge";
import {
  consumeCanvasRequest,
  subscribeCanvasRequests,
} from "@/lib/canvas-request-store";
import {
  DuplicateAssetError,
  ingestAsset,
  listLibraries,
  patchLibrary,
  type AssetLibrary,
} from "@/lib/library-api";
import {
  notifyLibraryDataChanged,
  openLibraryPanel,
} from "@/library/library-panel-store";

const NEW_LIBRARY = "__new__";

export function LibraryIngestDialog() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [libraries, setLibraries] = useState<AssetLibrary[]>([]);
  const [libraryChoice, setLibraryChoice] = useState("");
  const [newName, setNewName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [title, setTitle] = useState("");
  const [keywords, setKeywords] = useState("");
  const [sourceProject, setSourceProject] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => {
      const next = consumeCanvasRequest("library-ingest");
      if (next) {
        setOpen(true);
        setBusy(false);
        setError(null);
        setProgress("");
        setTitle("");
        setNewName("");
        setPurpose("");
        setKeywords("");
        setSourceProject("");
        setCharacterName("");
        setForce(false);
        void exportSelectedImageFiles().then(setFiles).catch(() => setFiles([]));
      }
    };
    sync();
    return subscribeCanvasRequests(sync);
  }, []);

  useEffect(() => {
    if (!open) return;
    void listLibraries()
      .then((rows) => {
        setLibraries(rows);
        setLibraryChoice((current) => {
          const next = current || rows[0]?.id || NEW_LIBRARY;
          if (!current && rows[0]) setPurpose(rows[0].purpose ?? "");
          return next;
        });
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : "无法加载素材库");
      });
  }, [open]);

  const selectedLibrary = libraries.find((library) => library.id === libraryChoice);
  const creating = libraryChoice === NEW_LIBRARY;

  function handleClose() {
    if (busy) return;
    setOpen(false);
    setError(null);
  }

  function addLocalFiles(list: FileList | null) {
    if (!list) return;
    const extra = Array.from(list).filter(
      (file) =>
        file.type.startsWith("image/") ||
        /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name),
    );
    setFiles((current) => [...current, ...extra]);
  }

  async function handleSubmit() {
    setError(null);
    setBusy(true);
    try {
      if (files.length === 0) {
        const hint = getLibraryExportHint();
        setError(hint ?? "请选择要入库的图片，或从本地追加文件");
        return;
      }
      const libraryName = creating ? newName.trim() : "";
      if (creating && !libraryName) {
        setError("请输入新素材库名称");
        return;
      }
      const libraryId = creating ? undefined : libraryChoice;
      if (!creating && libraryId && purpose.trim() !== (selectedLibrary?.purpose ?? "")) {
        await patchLibrary(libraryId, { purpose: purpose.trim() });
      }
      const remaining: File[] = [];
      const skipped: string[] = [];
      const failures: string[] = [];
      let created = 0;
      for (const [index, file] of files.entries()) {
        setProgress(`${index + 1}/${files.length}`);
        try {
          await ingestAsset({
            image: file,
            libraryId,
            libraryName: creating ? libraryName : undefined,
            libraryPurpose: creating ? purpose.trim() : undefined,
            title: files.length === 1 ? title.trim() || undefined : undefined,
            keywords: keywords.trim() || undefined,
            sourceProject: sourceProject.trim() || undefined,
            characterName: characterName.trim() || undefined,
            force,
          });
          created += 1;
        } catch (exc: unknown) {
          if (exc instanceof DuplicateAssetError) {
            skipped.push(exc.existingTitle || file.name);
            remaining.push(file);
          } else {
            failures.push(exc instanceof Error ? exc.message : file.name);
            remaining.push(file);
          }
        }
      }
      if (created > 0) notifyLibraryDataChanged();
      setFiles(remaining);
      if (created > 0 && remaining.length === 0 && failures.length === 0) {
        setOpen(false);
        openLibraryPanel();
        return;
      }
      const parts: string[] = [];
      if (created) parts.push(`已入库 ${created} 张`);
      if (skipped.length) {
        parts.push(
          `重复 ${skipped.length} 张（${skipped.slice(0, 3).join("、")}${skipped.length > 3 ? "…" : ""}）。勾选「仍要入库」后可再提交`,
        );
      }
      if (failures.length) parts.push(`失败：${failures[0]}`);
      setError(parts.join("。") || "入库未完成");
      if (created > 0) openLibraryPanel();
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : "入库失败");
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-end justify-end bg-black/50 p-6 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label="加入素材库"
      onClick={handleClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-line bg-surface-1 p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-2 text-accent">
            <ImageIcon size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-ink">加入素材库</h2>
            <p className="text-[11px] text-muted">
              可指定库名或新建库。多选与本地文件将批量入库，相同内容会按哈希去重。
            </p>
          </div>
        </div>

        {error ? (
          <p className="mb-3 flex items-start gap-1.5 text-[11px] text-warning">
            <AlertIcon size={13} className="mt-px shrink-0" />
            {error}
          </p>
        ) : null}

        <label className="mb-2 block text-[11px] text-muted">归入素材库</label>
        <select
          className="mb-3 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          value={libraryChoice}
          disabled={busy}
          onChange={(event) => {
            const value = event.target.value;
            setLibraryChoice(value);
            if (value !== NEW_LIBRARY) {
              const chosen = libraries.find((library) => library.id === value);
              setPurpose(chosen?.purpose ?? "");
            }
          }}
        >
          {libraries.map((library) => (
            <option key={library.id} value={library.id}>
              {library.name}
              {library.purpose ? ` · ${library.purpose}` : ""}
            </option>
          ))}
          <option value={NEW_LIBRARY}>新建素材库…</option>
        </select>

        {creating ? (
          <input
            className="mb-2 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
            placeholder="新库名称"
            value={newName}
            disabled={busy}
            onChange={(event) => setNewName(event.target.value)}
          />
        ) : null}
        <textarea
          className="mb-3 min-h-[56px] w-full resize-none rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          placeholder="用途说明，例如：女骑士可复用部件"
          value={purpose}
          disabled={busy}
          onChange={(event) => setPurpose(event.target.value)}
        />

        <label className="mb-2 block text-[11px] text-muted">
          标题（仅单张时生效，留空则用模型命名）
        </label>
        <input
          className="mb-3 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          placeholder="例如：红披风骑士"
          value={title}
          disabled={busy || files.length > 1}
          onChange={(event) => setTitle(event.target.value)}
        />

        <label className="mb-2 block text-[11px] text-muted">关键词（逗号分隔）</label>
        <input
          className="mb-3 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          placeholder="持剑, 全身, 可拆解"
          value={keywords}
          disabled={busy}
          onChange={(event) => setKeywords(event.target.value)}
        />
        <div className="mb-3 grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[11px] text-muted">来源项目</label>
            <input
              className="w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
              placeholder="骑士demo"
              value={sourceProject}
              disabled={busy}
              onChange={(event) => setSourceProject(event.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-muted">角色归属</label>
            <input
              className="w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
              placeholder="女剑士"
              value={characterName}
              disabled={busy}
              onChange={(event) => setCharacterName(event.target.value)}
            />
          </div>
        </div>

        <p className="mb-2 text-[11px] text-muted">
          待入库 {files.length} 张
          {files.length > 0 ? `：${files.map((file) => file.name).slice(0, 3).join("、")}` : ""}
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(event) => {
            addLocalFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="mb-3 rounded-lg border border-line px-3 py-1.5 text-xs hover:bg-surface-2"
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
        >
          追加本地文件
        </button>

        <label className="mb-4 flex items-center gap-2 text-[11px] text-muted">
          <input
            type="checkbox"
            checked={force}
            disabled={busy}
            onChange={(event) => setForce(event.target.checked)}
          />
          仍要入库（忽略内容重复）
        </label>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg px-3 py-1.5 text-xs text-muted hover:bg-surface-2"
            disabled={busy}
            onClick={handleClose}
          >
            取消
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            disabled={busy}
            onClick={() => void handleSubmit()}
          >
            {busy ? <Spinner size={12} /> : null}
            {busy ? `标注并入库… ${progress}` : files.length > 1 ? `入库 ${files.length} 张` : "入库"}
          </button>
        </div>
      </div>
    </div>
  );
}
