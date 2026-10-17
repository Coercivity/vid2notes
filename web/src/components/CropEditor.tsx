import { PointerEvent, useRef, useState } from "react";
import { Crop } from "../api";

type Mode = "move" | "new" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

interface Drag {
  mode: Mode;
  start: { x: number; y: number };
  origin: Crop;
}

interface Props {
  previews: string[];
  crop: Crop;
  onChange: (crop: Crop) => void;
}

const MIN_SIZE = 0.02;
const HANDLES: Mode[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

function resize(origin: Crop, mode: Mode, dx: number, dy: number): Crop {
  let left = origin.x;
  let top = origin.y;
  let right = origin.x + origin.width;
  let bottom = origin.y + origin.height;
  if (mode.includes("w")) left = clamp(left + dx, 0, right - MIN_SIZE);
  if (mode.includes("e")) right = clamp(right + dx, left + MIN_SIZE, 1);
  if (mode.includes("n")) top = clamp(top + dy, 0, bottom - MIN_SIZE);
  if (mode.includes("s")) bottom = clamp(bottom + dy, top + MIN_SIZE, 1);
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function span(a: { x: number; y: number }, b: { x: number; y: number }): Crop {
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  return {
    x,
    y,
    width: Math.max(Math.abs(a.x - b.x), MIN_SIZE),
    height: Math.max(Math.abs(a.y - b.y), MIN_SIZE),
  };
}

export function CropEditor({ previews, crop, onChange }: Props) {
  const [selected, setSelected] = useState(0);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);

  const point = (event: PointerEvent) => {
    const rect = frame.current!.getBoundingClientRect();
    return {
      x: clamp((event.clientX - rect.left) / rect.width, 0, 1),
      y: clamp((event.clientY - rect.top) / rect.height, 0, 1),
    };
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const mode = (target.dataset.mode as Mode | undefined) ?? "new";
    drag.current = { mode, start: point(event), origin: crop };
    frame.current!.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current) return;
    const p = point(event);
    const dx = p.x - current.start.x;
    const dy = p.y - current.start.y;
    if (current.mode === "new") {
      onChange(span(current.start, p));
    } else if (current.mode === "move") {
      const { origin } = current;
      onChange({
        ...origin,
        x: clamp(origin.x + dx, 0, 1 - origin.width),
        y: clamp(origin.y + dy, 0, 1 - origin.height),
      });
    } else {
      onChange(resize(current.origin, current.mode, dx, dy));
    }
  };

  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    frame.current?.releasePointerCapture(event.pointerId);
  };

  const percent = (value: number) => `${(value * 100).toFixed(2)}%`;

  return (
    <div className="crop-editor">
      <div
        ref={frame}
        className="crop-frame"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <img src={previews[selected]} alt={`Frame ${selected + 1}`} draggable={false} />
        <div
          className="crop-rect"
          data-mode="move"
          style={{ left: percent(crop.x), top: percent(crop.y), width: percent(crop.width), height: percent(crop.height) }}
        >
          {HANDLES.map((handle) => (
            <span key={handle} className={`crop-handle crop-handle-${handle}`} data-mode={handle} />
          ))}
        </div>
      </div>
      <div className="thumbs">
        {previews.map((src, index) => (
          <button
            key={src}
            className={index === selected ? "thumb active" : "thumb"}
            onClick={() => setSelected(index)}
            type="button"
          >
            <img src={src} alt={`Frame ${index + 1}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
