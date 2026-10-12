"use client";

import { useEffect, useRef, useState, type PointerEvent } from "react";
import { maskPoint, polygonArea, type MaskPoint } from "./mask-edit";

type Tool = "lasso" | "polygon" | "brush" | "erase" | "positive" | "negative";
interface Props {
  imageUrl: string; width: number; height: number; maskUrl?: string | null;
  disabled: boolean;
  onSave: (mask: Blob) => void;
  onPoints: (points: number[][], labels: number[]) => void;
  onDirty: () => void;
}

export function MaskEditor({ imageUrl, width, height, maskUrl, disabled, onSave, onPoints, onDirty }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const backing = useRef<HTMLCanvasElement | null>(null);
  const history = useRef<ImageData[]>([]);
  const future = useRef<ImageData[]>([]);
  const path = useRef<MaskPoint[]>([]);
  const drawing = useRef(false);
  const [tool, setTool] = useState<Tool>("lasso");
  const [brush, setBrush] = useState(20);
  const [points, setPoints] = useState<{ point: MaskPoint; label: number }[]>([]);
  const [historySizes, setHistorySizes] = useState({ undo: 0, redo: 0 });

  function paint() {
    const target = canvas.current?.getContext("2d");
    if (!target || !backing.current) return;
    target.clearRect(0, 0, width, height);
    target.drawImage(backing.current, 0, 0);
    target.globalCompositeOperation = "source-in";
    target.fillStyle = "rgba(80,150,255,0.5)";
    target.fillRect(0, 0, width, height);
    target.globalCompositeOperation = "source-over";
    if (path.current.length) {
      target.beginPath();
      path.current.forEach((point, i) => i ? target.lineTo(point.x, point.y) : target.moveTo(point.x, point.y));
      target.strokeStyle = "#ffca55";
      target.lineWidth = Math.max(2, width / 250);
      target.stroke();
    }
  }

  useEffect(() => {
    const layer = document.createElement("canvas");
    layer.width = width; layer.height = height;
    backing.current = layer;
    history.current = []; future.current = [];
    const image = new Image();
    let active = true;
    if (maskUrl) {
      image.onload = () => {
        if (!active) return;
        const context = layer.getContext("2d")!;
        context.drawImage(image, 0, 0, width, height);
        const pixels = context.getImageData(0, 0, width, height);
        for (let i = 0; i < pixels.data.length; i += 4) {
          const keep = pixels.data[i] >= 128;
          pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 255;
          pixels.data[i + 3] = keep ? 255 : 0;
        }
        context.putImageData(pixels, 0, 0); paint();
      };
      image.src = maskUrl;
    } else {
      canvas.current?.getContext("2d")?.clearRect(0, 0, width, height);
    }
    return () => { active = false; };
    // Only reinitialize when the immutable source or selected mask changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height, maskUrl]);

  function checkpoint() {
    const context = backing.current?.getContext("2d");
    if (!context) return;
    history.current.push(context.getImageData(0, 0, width, height));
    if (history.current.length > 8) history.current.shift();
    future.current = []; onDirty(); setHistorySizes({ undo: history.current.length, redo: 0 });
  }
  function finishPolygon() {
    const context = backing.current?.getContext("2d");
    if (!context || path.current.length < 3 || polygonArea(path.current) < 1) return;
    checkpoint(); context.beginPath();
    path.current.forEach((point, i) => i ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
    context.closePath(); context.fillStyle = "white"; context.fill();
    path.current = []; paint();
  }
  function pointer(event: PointerEvent<HTMLCanvasElement>, phase: "down" | "move" | "up") {
    if (disabled) return;
    const point = maskPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), width, height);
    const context = backing.current?.getContext("2d");
    if (!context) return;
    if (phase === "down") {
      event.currentTarget.setPointerCapture(event.pointerId);
      if (tool === "positive" || tool === "negative") {
        const next = [...points, { point, label: tool === "positive" ? 1 : 0 }];
        setPoints(next); onPoints(next.map(p => [p.point.x / width, p.point.y / height]), next.map(p => p.label));
        return;
      }
      if (tool === "polygon") { path.current.push(point); paint(); return; }
      drawing.current = true; path.current = [point];
      if (tool === "brush" || tool === "erase") checkpoint();
    }
    if (!drawing.current) return;
    if (tool === "brush" || tool === "erase") {
      const previous = path.current[path.current.length - 1];
      context.globalCompositeOperation = tool === "erase" ? "destination-out" : "source-over";
      context.strokeStyle = "white"; context.fillStyle = "white";
      context.lineWidth = brush; context.lineCap = "round";
      context.beginPath(); context.moveTo(previous.x, previous.y); context.lineTo(point.x, point.y); context.stroke();
      context.beginPath(); context.arc(point.x, point.y, brush / 2, 0, Math.PI * 2); context.fill();
      context.globalCompositeOperation = "source-over";
    }
    path.current.push(point); paint();
    if (phase === "up") {
      drawing.current = false;
      if (tool === "lasso") finishPolygon();
      path.current = []; paint();
    }
  }
  function restore(undo: boolean) {
    const context = backing.current?.getContext("2d");
    const from = undo ? history.current : future.current;
    const to = undo ? future.current : history.current;
    const state = from.pop();
    if (!context || !state) return;
    to.push(context.getImageData(0, 0, width, height));
    context.putImageData(state, 0, 0); onDirty(); paint();
    setHistorySizes({ undo: history.current.length, redo: future.current.length });
  }
  function save() {
    const output = document.createElement("canvas");
    output.width = width; output.height = height;
    const context = output.getContext("2d")!;
    context.fillStyle = "black"; context.fillRect(0, 0, width, height);
    if (backing.current) context.drawImage(backing.current, 0, 0);
    output.toBlob(blob => { if (blob) onSave(blob); }, "image/png");
  }
  return <div className="space-y-2">
    <div className="flex flex-wrap gap-1">
      {([['lasso','套索'],['polygon','多边形'],['brush','画笔'],['erase','橡皮'],['positive','SAM 正点'],['negative','SAM 负点']] as const).map(([value,label]) =>
        <button type="button" key={value} disabled={disabled} aria-pressed={tool === value}
          className={`rounded border px-2 py-1 ${tool === value ? 'border-accent text-accent' : 'border-line'}`}
          onClick={() => { path.current = []; setTool(value); paint(); }}>{label}</button>)}
    </div>
    <label>画笔大小（源图像素）<input aria-label="画笔大小" type="range" min="1" max="200" value={brush} onChange={e => setBrush(Number(e.target.value))} /></label>
    <div className="relative w-full" style={{ aspectRatio: `${width}/${height}` }}>
      {/* eslint-disable-next-line @next/next/no-img-element -- owned artifact blob */}
      <img src={imageUrl} alt="圈选编辑区域" className="absolute inset-0 h-full w-full" draggable={false} />
      <canvas ref={canvas} width={width} height={height} className="absolute inset-0 h-full w-full touch-none"
        onPointerDown={e => pointer(e,'down')} onPointerMove={e => pointer(e,'move')} onPointerUp={e => pointer(e,'up')}
        onPointerCancel={() => { drawing.current = false; path.current = []; paint(); }} />
      {points.map((p,i) => <span key={i} className="pointer-events-none absolute rounded-full border border-white"
        style={{ left:`${p.point.x / width * 100}%`,top:`${p.point.y / height * 100}%`,width:8,height:8,
          background:p.label ? '#22cc88' : '#ff5555',transform:'translate(-50%,-50%)' }} />)}
    </div>
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={disabled} onClick={finishPolygon}>闭合多边形</button>
      <button type="button" disabled={!historySizes.undo || disabled} onClick={() => restore(true)}>撤销</button>
      <button type="button" disabled={!historySizes.redo || disabled} onClick={() => restore(false)}>重做</button>
      <button type="button" disabled={disabled} onClick={() => { checkpoint(); backing.current?.getContext('2d')?.clearRect(0,0,width,height); path.current=[]; setPoints([]); onPoints([],[]); paint(); }}>清空</button>
      <button type="button" disabled={disabled} className="text-accent" onClick={save}>确认 Mask</button>
    </div>
  </div>;
}
