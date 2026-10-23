import { useEffect, useRef, useState, type CSSProperties, type DragEvent } from "react";
import { capitalize, pct, type Result } from "../api";
import { UploadIcon } from "./icons";

export type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; progress: number }
  | { phase: "error"; message: string; detail?: string };

interface Props {
  src: string | null; // the photo to show: a local preview while uploading, else the stored original
  result: Result | null;
  upload: UploadState;
  onFile: (file: File) => void;
}

/**
 * Where the model looked. preprocess crops the centre square (ImageOps.fit) before resizing to
 * 224x224, so the square is the full short side, centred. Returned as percentages of the photo.
 */
function cropBox(width: number, height: number): CSSProperties {
  if (width >= height) {
    const w = (height / width) * 100;
    return { left: `${(100 - w) / 2}%`, top: 0, width: `${w}%`, height: "100%" };
  }
  const h = (width / height) * 100;
  return { left: 0, top: `${(100 - h) / 2}%`, width: "100%", height: `${h}%` };
}

const corner = "absolute h-5 w-5 border-white/95";

export default function Stage({ src, result, upload, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const busy = upload.phase === "uploading";

  useEffect(() => setSize(null), [src]);

  const choose = () => input.current?.click();
  const dropProps = {
    onDragEnter: (e: DragEvent) => { e.preventDefault(); setDragging(true); },
    onDragOver: (e: DragEvent) => { e.preventDefault(); setDragging(true); },
    onDragLeave: (e: DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && !busy) onFile(file);
    },
  };

  return (
    <section aria-label="Photo" {...dropProps}
      className={`rounded-2xl border bg-surface p-3 shadow-soft transition-colors ${
        dragging ? "border-accent" : "border-line"
      }`}>
      <input ref={input} type="file" accept="image/jpeg,image/png" className="sr-only" tabIndex={-1}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onFile(f); }} />

      {src ? (
        <div className="flex h-[22rem] items-center justify-center rounded-xl bg-raised sm:h-[28rem]">
          {/* The wrapper shrink-wraps the photo, so overlays can be placed in % of the photo. */}
          <div className="relative inline-block max-h-full max-w-full overflow-hidden rounded-lg">
            <img src={src} alt={result ? `Your photo, classified as ${result.label}` : "Your photo"}
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              className="block max-h-[22rem] max-w-full sm:max-h-[28rem]" />

            {busy && (
              <div className="absolute inset-0" aria-hidden="true">
                <div className="pixel-grid absolute inset-0 opacity-70" />
                <div className="scanline" />
              </div>
            )}

            {!busy && result && size && (
              <div key={result.imageId} className="focus-in absolute" style={cropBox(size.w, size.h)}>
                {/* Everything outside the square is dimmed: the model never saw it. */}
                <div className="absolute inset-0 shadow-[0_0_0_9999px_rgb(0_0_0/0.45)]" />
                <span className={`${corner} left-2 top-2 rounded-tl-md border-l-2 border-t-2`} />
                <span className={`${corner} right-2 top-2 rounded-tr-md border-r-2 border-t-2`} />
                <span className={`${corner} bottom-2 left-2 rounded-bl-md border-b-2 border-l-2`} />
                <span className={`${corner} bottom-2 right-2 rounded-br-md border-b-2 border-r-2`} />
                <span className="rise absolute left-9 top-2.5 rounded-full bg-black/60 px-3 py-1 text-sm font-medium text-white backdrop-blur"
                  style={{ "--delay": "350ms" } as CSSProperties}>
                  {capitalize(result.label)} <span className="font-normal text-white/75">{pct(result.confidence)}</span>
                </span>
              </div>
            )}

            {busy && (
              <div className="absolute inset-x-0 bottom-0 h-1 bg-black/20">
                <div className="h-full bg-accent transition-[width] duration-200"
                  style={{ width: `${Math.max(upload.progress, 0.04) * 100}%` }} />
              </div>
            )}
          </div>
        </div>
      ) : (
        <button type="button" onClick={choose}
          className={`pixel-grid flex h-[22rem] w-full flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed text-center transition-all sm:h-[28rem] ${
            dragging ? "scale-[0.99] border-accent bg-accent/5" : "border-line hover:border-accent/60"
          }`}>
          <span className="grid h-14 w-14 place-items-center rounded-full bg-accent/10 text-accent">
            <UploadIcon width={26} height={26} />
          </span>
          <span>
            <span className="block text-lg font-semibold">Drop a photo to classify it</span>
            <span className="mt-1 block text-sm text-muted">JPEG or PNG, up to 8 MB</span>
          </span>
          <span className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white shadow-soft">
            Choose a photo
          </span>
        </button>
      )}

      {src && (
        <div className="flex min-h-12 flex-wrap items-center justify-between gap-3 px-1 pt-3">
          <p className="text-sm text-muted" aria-live="polite">
            {busy
              ? upload.progress < 1
                ? `Uploading ${upload.name}, ${Math.round(upload.progress * 100)}%`
                : `Classifying ${upload.name}…`
              : result
                ? "The bright square is what the model saw, scaled to 224 × 224."
                : ""}
          </p>
          <button type="button" onClick={choose} disabled={busy}
            className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white shadow-soft transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50">
            <UploadIcon width={16} height={16} /> New photo
          </button>
        </div>
      )}

      {upload.phase === "error" && (
        <div role="alert" className="rise mx-1 mb-1 mt-1 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          <p className="font-medium">{upload.message}</p>
          {upload.detail && <p className="mt-0.5 text-xs opacity-80">{upload.detail}</p>}
        </div>
      )}
    </section>
  );
}
