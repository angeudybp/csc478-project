import type { CSSProperties } from "react";
import {
  capitalize, downloadName, downloadUrl, imageUrl, pct, podSuffix, type Result, type Variant,
} from "../api";
import { useRevealed } from "../hooks";
import { DownloadIcon } from "./icons";

const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as CSSProperties;

function ConfidenceRing({ value, revealed }: { value: number; revealed: boolean }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative h-20 w-20 shrink-0" role="img" aria-label={`${pct(value)} confident`}>
      <svg viewBox="0 0 72 72" className="h-full w-full -rotate-90">
        <circle cx="36" cy="36" r={r} fill="none" strokeWidth="6" className="stroke-line" />
        <circle cx="36" cy="36" r={r} fill="none" strokeWidth="6" strokeLinecap="round"
          className="stroke-accent transition-[stroke-dashoffset] duration-1000 ease-out"
          strokeDasharray={c} strokeDashoffset={revealed ? c * (1 - value) : c} />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

function DownloadCard({ result, variant, title, detail, wait }: {
  result: Result; variant: Variant; title: string; detail: string; wait: number;
}) {
  const ext = variant === "original" && /\.png$/i.test(result.filename ?? "") ? "png" : "jpg";
  return (
    <a href={downloadUrl(result.imageId, variant)} download style={delay(wait)}
      className="rise group flex items-center gap-3 rounded-xl border border-line bg-raised p-2.5 pr-4 transition hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-lift">
      <img src={imageUrl(result.imageId, "processed")} alt=""
        className="h-12 w-12 shrink-0 rounded-lg object-cover" />
      <span className="min-w-0">
        <span className="block font-medium">{title}</span>
        <span className="block text-xs text-muted">{detail}</span>
        <span className="block truncate text-xs text-muted" title={downloadName(result, variant, ext)}>
          {downloadName(result, variant, ext)}
        </span>
      </span>
      <DownloadIcon className="ml-auto shrink-0 text-accent transition-transform group-hover:translate-y-0.5" />
    </a>
  );
}

export default function ResultPanel({ result, busy }: { result: Result | null; busy: boolean }) {
  const revealed = useRevealed(result?.imageId);

  if (busy) {
    return (
      <section aria-label="Prediction" aria-busy="true" className="space-y-4 p-1">
        <div className="shimmer h-10 w-3/4 rounded-lg" />
        <div className="shimmer h-4 w-1/3 rounded" />
        <div className="space-y-3 pt-4">
          {[0, 1, 2].map((i) => <div key={i} className="shimmer h-3 rounded-full" />)}
        </div>
        <div className="shimmer mt-6 h-16 rounded-xl" />
        <div className="shimmer h-16 rounded-xl" />
      </section>
    );
  }

  if (!result) {
    return (
      <section aria-labelledby="intro" className="flex h-full flex-col justify-center p-1">
        <h1 id="intro" className="text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
          What's in your photo?
        </h1>
        <p className="mt-4 max-w-md text-lg text-muted">
          Drop a photo and it travels through four Kubernetes services, coming back with a label from
          MobileNetV2, a model that knows 1,000 animals and everyday objects.
        </p>
        <p className="mt-3 max-w-md text-muted">
          You can then download your original or the exact 224 × 224 image the model looked at.
        </p>
      </section>
    );
  }

  const t = result.timings;
  return (
    <section key={result.imageId} aria-labelledby="prediction" className="p-1">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 id="prediction" className="rise text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            {capitalize(result.label)}
          </h1>
          <p className="rise mt-2 text-muted" style={delay(80)}>
            {pct(result.confidence)} confident
            {result.mock && <span className="ml-2 rounded-full bg-focus/15 px-2 py-0.5 text-xs font-medium text-focus">mock model</span>}
          </p>
        </div>
        <ConfidenceRing value={result.confidence} revealed={revealed} />
      </div>

      <ol className="mt-6 space-y-3" aria-label="Top predictions">
        {result.topK.map((k, i) => (
          <li key={k.label} className="rise" style={delay(150 + i * 70)}>
            <div className="flex justify-between gap-3 text-sm">
              <span className={i === 0 ? "font-medium" : "text-muted"}>{capitalize(k.label)}</span>
              <span className="text-muted">{pct(k.score)}</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line">
              <div className={`h-full rounded-full transition-[width] duration-700 ease-out ${i === 0 ? "bg-accent" : "bg-muted/50"}`}
                style={{ width: revealed ? `${Math.max(k.score * 100, 1.5)}%` : "0%", transitionDelay: `${200 + i * 90}ms` }} />
            </div>
          </li>
        ))}
      </ol>

      <h2 className="rise mt-8 text-sm font-semibold" style={delay(380)}>Downloads</h2>
      <div className="mt-3 grid gap-3">
        <DownloadCard result={result} variant="original" title="Original photo" wait={420}
          detail={result.originalSize ? `${result.originalSize.width} × ${result.originalSize.height}, as uploaded` : "As uploaded"} />
        <DownloadCard result={result} variant="processed" title="What the model saw" wait={490}
          detail="224 × 224, centre crop" />
      </div>

      <dl className="rise mt-6 grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-1 text-sm" style={delay(560)}>
        <dt className="text-muted">Served by</dt>
        <dd className="truncate">replica {podSuffix(result.servedBy?.inferencePod)} on {result.servedBy?.inferenceNode ?? "?"}</dd>
        <dt className="text-muted">Time</dt>
        <dd className="tabular-nums">{t.totalMs} ms end to end</dd>
        <dt className="text-muted">Model</dt>
        <dd className="truncate">{result.modelVersion}</dd>
        <dt className="text-muted">Image ID</dt>
        <dd className="truncate">{result.imageId}</dd>
      </dl>
    </section>
  );
}
