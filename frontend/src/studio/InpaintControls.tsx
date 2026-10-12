"use client";

import { useEffect, useRef, useState } from "react";
import {
  fetchArtifactBlobUrl, previewInpaint, segmentEditMask, segmentationCapabilities, uploadEditMask,
  type BBox, type EditVersion, type InpaintOptions, type InpaintPreview,
} from "@/lib/controlled-edit-api";
import { MaskEditor } from "./MaskEditor";
import { useArtifactUrl } from "./useArtifactUrl";

export const DEFAULT_INPAINT_OPTIONS: InpaintOptions = {
  threshold: 0.5, fill_holes: false, dilate_px: 8, feather_sigma_px: 4,
  context_from_mask_extend_factor: 2, min_context_px: 16, model: "wanx2.1-imageedit",
};
export interface LocalSelection { versionId: string; maskId: string; options: InpaintOptions }
interface Props {
  sessionId: string; version: EditVersion; bbox?: BBox | null; disabled: boolean;
  onSelection: (selection: LocalSelection | null) => void;
  onModeChange: (versionId: string, enabled: boolean) => void;
}

export function InpaintControls({ sessionId, version, bbox, disabled, onSelection, onModeChange }: Props) {
  const imageUrl = useArtifactUrl(version.image_artifact_id);
  const [enabled, setEnabled] = useState(false);
  const [maskId, setMaskId] = useState<string | null>(null);
  const [maskUrl, setMaskUrl] = useState<string | null>(null);
  const [maskRevision, setMaskRevision] = useState(0);
  const [options, setOptions] = useState(DEFAULT_INPAINT_OPTIONS);
  const [caps, setCaps] = useState({ sam2: false, sam3: false });
  const [points, setPoints] = useState<number[][]>([]);
  const [labels, setLabels] = useState<number[]>([]);
  const [provider, setProvider] = useState<"sam2" | "sam3">("sam2");
  const [text, setText] = useState("");
  const [candidates, setCandidates] = useState<{ id: string; score: number | null }[]>([]);
  const [preview, setPreview] = useState<InpaintPreview | null>(null);
  const cropUrl = useArtifactUrl(preview?.crop_artifact_id ?? null);
  const cropMaskUrl = useArtifactUrl(preview?.mask_artifact_id ?? null);
  const blendUrl = useArtifactUrl(preview?.blend_artifact_id ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef(true);
  const operation = useRef(0);
  useEffect(() => {
    active.current = true;
    segmentationCapabilities().then(value => { if (active.current) setCaps(value); }).catch(() => undefined);
    return () => { active.current = false; };
  }, []);
  useEffect(() => () => { if (maskUrl) URL.revokeObjectURL(maskUrl); }, [maskUrl]);
  function clearSelection() { operation.current++; setMaskId(null); setPreview(null); onSelection(null); }
  async function run<T>(task: () => Promise<T>, apply: (value: T) => void) {
    const id = ++operation.current; setBusy(true); setError(null);
    try { const value = await task(); if (active.current && id === operation.current) apply(value); }
    catch (err) { if (active.current && id === operation.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (active.current) setBusy(false); }
  }
  function selectMask(id: string) {
    void run(() => fetchArtifactBlobUrl(id), url => {
      setMaskUrl(url); setMaskRevision(n => n + 1); setMaskId(id); setPreview(null);
      setPoints([]); setLabels([]);
      onSelection({ versionId: version.id, maskId: id, options });
    });
  }
  function updateOptions(next: InpaintOptions) {
    setOptions(next); setPreview(null); operation.current++;
    if (maskId) onSelection({ versionId: version.id, maskId, options: next });
  }
  const pendingCandidate = candidates.length > 0 && !candidates.some((item) => item.id === maskId);
  const panel = "rounded border border-dashed border-line p-2 space-y-2";
  return <section className="mb-3 space-y-2 rounded border border-dashed border-line p-2 text-[11px]">
    <label className="flex gap-2"><input type="checkbox" checked={enabled} disabled={disabled}
      onChange={e => {
        setEnabled(e.target.checked); onModeChange(version.id, e.target.checked);
        if (!e.target.checked) { clearSelection(); setCandidates([]); }
      }} />局部 Mask 编辑（裁剪后重绘）</label>
    {enabled && imageUrl && version.width && version.height ? <>
      <p className="text-muted">只发送局部图与 Mask；最终羽化范围外保留原图。当前模型：万相 2.1。</p>
      <div className={panel}>
        <MaskEditor key={`${version.id}-${maskRevision}`} imageUrl={imageUrl} width={version.width} height={version.height}
          maskUrl={maskUrl} disabled={busy || disabled} onDirty={clearSelection}
          onPoints={(p,l) => { setPoints(p); setLabels(l); }}
          onSave={blob => void run(() => uploadEditMask(sessionId, version.id, blob), mask => {
            setCandidates([]); setMaskId(mask.artifact_id); setPreview(null);
            onSelection({ versionId: version.id, maskId: mask.artifact_id, options });
          })} />
      </div>
      <div className={panel}>
        <div className="flex flex-wrap gap-2">
          <select aria-label="分割模型" className="rounded border border-dashed border-line bg-transparent px-1" value={provider} onChange={e => setProvider(e.target.value as 'sam2'|'sam3')}>
            <option value="sam2">SAM 2.1{caps.sam2 ? '' : '（未就绪）'}</option>
            <option value="sam3">SAM 3{caps.sam3 ? '' : '（未配置）'}</option>
          </select>
          <button type="button" className="rounded border border-dashed border-line px-2 py-1" disabled={busy || disabled || !caps[provider] || (!bbox && !points.length && !text)}
            onClick={() => void run(() => segmentEditMask(sessionId,version.id,{
              provider, ...(bbox ? {bbox} : {}), points, labels, ...(provider === 'sam3' && text ? {text} : {}),
            }), values => {
              setMaskId(null); setMaskUrl(null); setPreview(null); onSelection(null);
              setCandidates(values.map(m => ({id:m.artifact_id, score:m.score})));
            })}>自动分割</button>
        </div>
        {provider === 'sam3' ? <input aria-label="分割对象描述" className="w-full rounded border border-dashed border-line px-1" value={text} onChange={e => setText(e.target.value)} placeholder="例如：骑士手中的剑" /> : null}
        <p className="text-muted">使用选中实体框或 SAM 正点/负点。自动分割不可用时可手工圈选。</p>
      </div>
      {candidates.length ? <div className={`${panel} ${pendingCandidate ? "border-warning bg-warning/10" : ""}`} role={pendingCandidate ? "status" : undefined}>
        {pendingCandidate ? (
          <p className="flex items-center gap-1.5 font-medium text-warning">
            <span aria-hidden className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-warning text-[10px] leading-none">!</span>
            请选择一个候选 Mask，才会叠到图上
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">{candidates.map((m,i) => <button type="button" key={m.id} disabled={busy}
          className={`rounded border border-dashed px-2 py-1 ${m.id === maskId ? "border-accent text-accent" : pendingCandidate ? "border-warning text-warning" : "border-line"}`}
          onClick={() => selectMask(m.id)}>
          {pendingCandidate && i === 0 ? <span aria-hidden className="mr-1">!</span> : null}
          候选 {i+1}（{m.score?.toFixed(2)}）
        </button>)}</div>
      </div> : null}
      {(version.masks ?? []).length ? <div className={panel}>
        <select aria-label="历史 Mask" className="w-full rounded border border-dashed border-line bg-transparent px-1" value="" disabled={busy} onChange={e => selectMask(e.target.value)}>
          <option value="">恢复本版本已保存的 Mask…</option>{version.masks?.map((m,i) => <option key={m.artifact_id} value={m.artifact_id}>{i+1} · {m.source}</option>)}
        </select>
      </div> : null}
      <div className={`${panel} grid grid-cols-2 gap-2`}>
        {([
          ['threshold','阈值',0.01,1,0.05],['dilate_px','膨胀像素',0,128,1],
          ['feather_sigma_px','羽化像素',0,64,1],['context_from_mask_extend_factor','上下文倍数',1,8,0.1],
          ['min_context_px','最小上下文像素',0,512,1],
        ] as const).map(([name,label,min,max,step]) => <label key={name}>{label}<input className="w-full rounded border border-dashed border-line"
          type="number" min={min} max={max} step={step} value={options[name]} disabled={busy}
          onChange={e => { const value = Number(e.target.value); if(Number.isFinite(value) && value >= min && value <= max) updateOptions({...options,[name]:value}); }} /></label>)}
        <label><input type="checkbox" checked={options.fill_holes} disabled={busy} onChange={e => updateOptions({...options,fill_holes:e.target.checked})} />填充封闭空洞</label>
      </div>
      <div className={panel}>
        <button type="button" className="rounded border border-dashed border-accent px-2 py-1 text-accent" disabled={!maskId || busy || disabled}
          onClick={() => void run(() => previewInpaint(sessionId,version.id,maskId!,options), setPreview)}>预览裁剪与 Mask（不生成）</button>
        <p>{busy ? '处理中…' : maskId ? 'Mask 已确认；提交下方指令即可局部重绘。' : pendingCandidate ? '还有候选未选择。' : '请先确认 Mask。'}</p>
        {error ? <p role="alert" className="text-danger">{error}</p> : null}
        {preview ? <div className="space-y-1 rounded border border-dashed border-line p-2"><p>裁剪坐标：{preview.stitcher.crop_rect.join(', ')} · 工作尺寸 {preview.stitcher.model_size.join('×')}</p>
          <div className="grid grid-cols-3 gap-1">{([[cropUrl,'上下文裁剪'],[cropMaskUrl,'生成 Mask'],[blendUrl,'融合 Mask']] as const).map(([url,label]) => url ?
            <figure key={label} className="rounded border border-dashed border-line p-1">
              {/* eslint-disable-next-line @next/next/no-img-element -- artifact preview */}
              <img src={url} alt={label} className="w-full" /><figcaption>{label}</figcaption>
            </figure> : null)}</div>
        </div> : null}
      </div>
    </> : null}
  </section>;
}
