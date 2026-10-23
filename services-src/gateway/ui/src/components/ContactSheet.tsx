import { imageUrl, podSuffix, type Result } from "../api";

interface Props {
  results: Result[];
  selectedId?: string;
  error: string | null;
  onSelect: (r: Result) => void;
  onRefresh: () => void;
}

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/** Recent uploads laid out like a photographer's contact sheet, using the small 224 px copies. */
export default function ContactSheet({ results, selectedId, error, onSelect, onRefresh }: Props) {
  return (
    <section className="mt-12" aria-labelledby="sheet-heading">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="sheet-heading" className="text-xl font-semibold tracking-tight">Recent uploads</h2>
        <button type="button" onClick={onRefresh}
          className="rounded text-sm text-graphite underline-offset-4 hover:text-frame hover:underline">
          Refresh
        </button>
      </div>

      {error && <p className="mt-4 text-sm text-alert" role="alert">Couldn't load recent uploads: {error}</p>}
      {!error && results.length === 0 && (
        <p className="mt-4 text-graphite">No uploads yet. Every image you classify is kept here.</p>
      )}

      <ul className="mt-4 grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {results.map((r) => {
          const selected = r.imageId === selectedId;
          return (
            <li key={r.imageId}>
              <button type="button" onClick={() => onSelect(r)} aria-pressed={selected}
                className="group block w-full rounded-md text-left">
                <img src={imageUrl(r.imageId, "processed")} alt="" loading="lazy"
                  className={`aspect-square w-full rounded-md border bg-sheet object-cover transition-shadow ${
                    selected ? "border-marker ring-2 ring-marker" : "border-rule group-hover:border-graphite"
                  }`} />
                <span className="mt-1.5 block truncate text-sm font-medium first-letter:uppercase">{r.label}</span>
                <span className="flex justify-between gap-2 text-xs text-graphite">
                  <span className="truncate" title={r.servedBy?.inferencePod}>{podSuffix(r.servedBy?.inferencePod)}</span>
                  <span>{time(r.createdAt)}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
