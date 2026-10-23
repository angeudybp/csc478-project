import type { CSSProperties } from "react";
import { capitalize, downloadUrl, imageUrl, pct, type Result } from "../api";
import { DownloadIcon } from "./icons";

interface Props {
  results: Result[];
  selectedId?: string;
  error: string | null;
  onSelect: (r: Result) => void;
  onRefresh: () => void;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Every photo uploaded so far, newest first, with both downloads one click away. */
export default function Gallery({ results, selectedId, error, onSelect, onRefresh }: Props) {
  return (
    <section className="mt-16" aria-labelledby="gallery-heading">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="gallery-heading" className="text-2xl font-semibold tracking-tight">
          Your photos {results.length > 0 && <span className="text-muted">{results.length}</span>}
        </h2>
        <button type="button" onClick={onRefresh}
          className="rounded-full px-3 py-1 text-sm text-muted transition hover:bg-surface hover:text-ink">
          Refresh
        </button>
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-danger">Couldn't load your photos: {error}</p>}
      {!error && results.length === 0 && (
        <p className="mt-4 rounded-2xl border border-dashed border-line px-6 py-10 text-center text-muted">
          Nothing here yet. Photos you classify are kept here, ready to download.
        </p>
      )}

      <ul className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {results.map((r, i) => {
          const selected = r.imageId === selectedId;
          return (
            <li key={r.imageId} className="rise" style={{ "--delay": `${Math.min(i, 12) * 45}ms` } as CSSProperties}>
              <div className={`group relative overflow-hidden rounded-2xl border bg-surface shadow-soft transition duration-300 hover:-translate-y-1 hover:shadow-lift ${
                selected ? "border-accent ring-2 ring-accent/40" : "border-line"
              }`}>
                <button type="button" onClick={() => onSelect(r)} aria-pressed={selected}
                  className="block w-full text-left">
                  <span className="block overflow-hidden">
                    <img src={imageUrl(r.imageId, "processed")} alt="" loading="lazy"
                      className="aspect-square w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                  </span>
                  <span className="block p-3">
                    <span className="block truncate font-medium">{capitalize(r.label)}</span>
                    <span className="mt-0.5 flex justify-between gap-2 text-xs text-muted">
                      <span>{pct(r.confidence)}</span>
                      <span>{when(r.createdAt)}</span>
                    </span>
                  </span>
                </button>
                {/* Always visible on touch-size screens (no hover there); revealed on hover above that. */}
                <div className="absolute inset-x-2 top-2 flex justify-end gap-1.5 transition-opacity duration-200 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                  {([["original", "Original"], ["processed", "224px"]] as const).map(([variant, text]) => (
                    <a key={variant} href={downloadUrl(r.imageId, variant)} download
                      aria-label={`Download ${variant === "original" ? "the original photo" : "the 224 × 224 model input"} of ${r.label}`}
                      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-black/60 px-2 py-1 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80">
                      <DownloadIcon width={13} height={13} /> {text}
                    </a>
                  ))}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
