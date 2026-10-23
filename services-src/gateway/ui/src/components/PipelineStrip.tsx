import type { CSSProperties, ReactNode } from "react";
import { podSuffix, type Result } from "../api";

interface Props {
  result: Result | null;
  recent: Result[];
  routeKey: number; // Changes whenever the route should replay its animation.
}

interface Lane {
  pod: string;
  node?: string;
  count: number;
}

const STEP_MS = 140; // Delay between hops as the route lights up.
const MAX_LANES = 6;

/** Inference replicas seen in recent uploads, with how many requests each one served. */
function lanesFrom(recent: Result[], current: Result | null): { lanes: Lane[]; hidden: number } {
  const byPod = new Map<string, Lane>();
  for (const r of current ? [current, ...recent] : recent) {
    const pod = r.servedBy?.inferencePod;
    if (!pod) continue;
    const lane = byPod.get(pod) ?? { pod, node: r.servedBy?.inferenceNode, count: 0 };
    if (r !== current || !recent.some((x) => x.imageId === r.imageId)) lane.count += 1;
    byPod.set(pod, lane);
  }
  const sorted = [...byPod.values()].sort((a, b) => b.count - a.count || a.pod.localeCompare(b.pod));
  const active = current?.servedBy?.inferencePod;
  let shown = sorted.slice(0, MAX_LANES);
  if (active && !shown.some((l) => l.pod === active)) {
    shown = [...shown.slice(0, MAX_LANES - 1), byPod.get(active)!];
  }
  return { lanes: shown, hidden: sorted.length - shown.length };
}

function Connector({ lit, delay }: { lit: boolean; delay: number }) {
  return (
    // On wide screens the line sits level with the stage titles.
    <div className="flex items-center justify-center md:mt-[1.6rem] md:px-1" aria-hidden="true">
      <div className="relative h-6 w-px bg-rule md:h-px md:w-full md:min-w-6">
        {lit && (
          <span
            className="route-segment absolute inset-0 bg-marker md:-inset-y-px"
            style={{ "--delay": `${delay}ms` } as CSSProperties}
          />
        )}
      </div>
    </div>
  );
}

function Stage({ name, role, ms, lit, delay, children }: {
  name: string;
  role: string;
  ms?: number;
  lit: boolean;
  delay: number;
  children?: ReactNode;
}) {
  return (
    <div
      className={`rounded-md border bg-sheet p-4 ${lit ? "stage-lit border-marker" : "border-rule"}`}
      style={{ "--delay": `${delay}ms` } as CSSProperties}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">{name}</h3>
        <span className={`text-sm tabular-nums ${lit ? "text-frame" : "text-graphite"}`}>
          {ms === undefined ? "–" : ms < 1 ? "<1 ms" : `${ms} ms`}
        </span>
      </div>
      <p className="mt-1 text-sm leading-snug text-graphite">{role}</p>
      {children}
    </div>
  );
}

export default function PipelineStrip({ result, recent, routeKey }: Props) {
  const lit = result !== null;
  const t = result?.timings;
  const gatewayMs = t ? Math.max(0, t.totalMs - t.preprocessMs - t.inferenceMs - t.storageMs) : undefined;
  const { lanes, hidden } = lanesFrom(recent, result);
  const max = Math.max(1, ...lanes.map((l) => l.count));
  const multiNode = new Set(lanes.map((l) => l.node)).size > 1;
  const active = result?.servedBy?.inferencePod;

  return (
    <section className="mt-10" aria-labelledby="route-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 id="route-heading" className="text-xl font-semibold tracking-tight">
          {result ? "How the cluster handled this image" : "The pipeline"}
        </h2>
        <p className="text-sm tabular-nums text-graphite">
          {t ? `${t.totalMs} ms end to end` : "Upload an image to trace its route."}
        </p>
      </div>

      {/* key replays the route animation for each new request. */}
      <div
        key={routeKey}
        className="mt-4 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)_2rem_minmax(0,1.5fr)_2rem_minmax(0,1fr)] md:items-start"
      >
        <Stage name="gateway" role="Checks the upload, then calls each service in turn." ms={gatewayMs}
          lit={lit} delay={0} />
        <Connector lit={lit} delay={STEP_MS} />
        <Stage name="preprocess" role="Strips metadata and resizes to 224 × 224." ms={t?.preprocessMs}
          lit={lit} delay={STEP_MS * 2} />
        <Connector lit={lit} delay={STEP_MS * 3} />
        <Stage name="inference" role="Labels the image. The Service picks one replica per request."
          ms={t?.inferenceMs} lit={lit} delay={STEP_MS * 4}>
          {lanes.length > 0 ? (
            <ul className="mt-3 space-y-1.5" aria-label="Inference replicas">
              {lanes.map((lane) => {
                const isActive = lane.pod === active;
                return (
                  <li
                    key={lane.pod}
                    title={lane.pod}
                    className={`grid grid-cols-[5.5rem_minmax(0,1fr)_2rem] items-center gap-2 rounded px-2 py-1 text-sm ${
                      isActive ? "bg-marker/15 font-medium" : ""
                    }`}
                  >
                    <span className="truncate">
                      {podSuffix(lane.pod)}
                      {multiNode && lane.node && <span className="block text-xs text-graphite">{lane.node}</span>}
                    </span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-rule">
                      <span
                        className={`block h-full rounded-full ${isActive ? "bg-marker" : "bg-graphite"}`}
                        style={{ width: `${(lane.count / max) * 100}%` }}
                      />
                    </span>
                    <span className="text-right tabular-nums text-graphite">{lane.count}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-graphite">Replicas appear here after the first upload.</p>
          )}
          {lanes.length > 0 && (
            <p className="mt-2 text-xs leading-snug text-graphite">
              Requests per replica over the last {recent.length} uploads
              {hidden > 0 ? `, plus ${hidden} older replica${hidden === 1 ? "" : "s"} not shown` : ""}.
              {active ? " Highlighted: the replica that served this image." : ""}
            </p>
          )}
        </Stage>
        <Connector lit={lit} delay={STEP_MS * 5} />
        <Stage name="storage" role="Saves the original, the 224 px copy and the result." ms={t?.storageMs}
          lit={lit} delay={STEP_MS * 6} />
      </div>
    </section>
  );
}
