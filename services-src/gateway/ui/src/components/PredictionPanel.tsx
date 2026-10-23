import { imageUrl, type Result } from "../api";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export default function PredictionPanel({ result }: { result: Result | null }) {
  if (!result) {
    return (
      <section aria-labelledby="prediction-heading">
        <h2 id="prediction-heading" className="text-xl font-semibold tracking-tight">Prediction</h2>
        <p className="mt-4 max-w-prose text-graphite">
          Upload an image to see its label, how confident the model is, and the exact 224 × 224 input
          the model received.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="prediction-heading">
      <h2 id="prediction-heading" className="sr-only">Prediction</h2>
      <p className="text-5xl font-semibold leading-none tracking-tight first-letter:uppercase sm:text-6xl">
        {result.label}
      </p>
      <p className="mt-3 text-graphite">
        {pct(result.confidence)} confident
        {result.mock && (
          <span title="Mock mode: labels are repeatable placeholders until the real model ships in Milestone 3.">
            , from the mock model
          </span>
        )}
      </p>

      <ol className="mt-5 space-y-2" aria-label="Top labels">
        {result.topK.map((k, i) => (
          <li key={k.label} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
            <span className={`truncate ${i === 0 ? "font-medium" : "text-graphite"}`}>{k.label}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-rule">
              <span className={`block h-full rounded-full ${i === 0 ? "bg-frame" : "bg-graphite/60"}`}
                style={{ width: `${Math.max(k.score * 100, 1)}%` }} />
            </span>
            <span className="text-right text-graphite">{pct(k.score)}</span>
          </li>
        ))}
      </ol>

      <div className="mt-6 grid grid-cols-2 gap-3">
        <figure>
          <img src={imageUrl(result.imageId, "original")} alt={`Original upload${result.filename ? `, ${result.filename}` : ""}`}
            className="aspect-square w-full rounded-md border border-rule bg-sheet object-contain" />
          <figcaption className="mt-1.5 text-xs text-graphite">
            What you uploaded{result.originalSize ? `, ${result.originalSize.width} × ${result.originalSize.height}` : ""}
          </figcaption>
        </figure>
        <figure>
          <img src={imageUrl(result.imageId, "processed")} alt="The 224 by 224 image the model received"
            className="aspect-square w-full rounded-md border border-rule bg-sheet object-contain" />
          <figcaption className="mt-1.5 text-xs text-graphite">What the model saw, 224 × 224</figcaption>
        </figure>
      </div>

      <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-0.5 text-xs text-graphite">
        <dt>Image ID</dt><dd className="truncate text-frame">{result.imageId}</dd>
        <dt>Request ID</dt><dd className="truncate text-frame">{result.requestId}</dd>
        <dt>Model</dt><dd className="truncate text-frame">{result.modelVersion}</dd>
      </dl>
    </section>
  );
}
