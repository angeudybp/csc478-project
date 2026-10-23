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

// The route plays in order: each stage lights up when the packet from the previous one arrives.
const STAGE_AT = [0, 450, 900, 1350];
const PACKET_AT = [70, 520, 970];
const MAX_LANES = 6;

const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as CSSProperties;

/** Inference replicas seen in recent uploads, with how many requests each one served. */
function lanesFrom(recent: Result[], current: Result | null): { lanes: Lane[]; hidden: number } {
  const byPod = new Map<string, Lane>();
  // Count every recent upload once; the current one too if it is not in the list yet.
  const counted = current && !recent.some((x) => x.imageId === current.imageId) ? [current, ...recent] : recent;
  for (const r of counted) {
    const pod = r.servedBy?.inferencePod;
    if (!pod) continue;
    const lane = byPod.get(pod) ?? { pod, node: r.servedBy?.inferenceNode, count: 0 };
    lane.count += 1;
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

function Connector({ lit, at }: { lit: boolean; at: number }) {
  return (
    <div className="flex justify-center md:mt-9 md:block md:px-1" aria-hidden="true">
      <div className="relative h-8 w-0.5 rounded-full bg-line md:h-0.5 md:w-full">
        {lit && <span className="packet" style={delay(at)} />}
      </div>
    </div>
  );
}

function Stage({ name, role, ms, lit, at, children }: {
  name: string; role: string; ms?: number; lit: boolean; at: number; children?: ReactNode;
}) {
  return (
    <div className={`rounded-2xl border border-line bg-surface p-4 shadow-soft ${lit ? "stage-lit" : ""}`}
      style={delay(at)}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">{name}</h3>
        <span className={`rounded-full px-2 py-0.5 text-xs tabular-nums ${lit ? "bg-focus/15 text-ink" : "bg-raised text-muted"}`}>
          {ms === undefined ? "–" : ms < 1 ? "<1 ms" : `${ms} ms`}
        </span>
      </div>
      <p className="mt-1 text-sm leading-snug text-muted">{role}</p>
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
    <section className="mt-14" aria-labelledby="route-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 id="route-heading" className="text-2xl font-semibold tracking-tight">
          {result ? "How the cluster handled it" : "How it works"}
        </h2>
        <p className="text-sm text-muted">
          {t ? `${t.totalMs} ms end to end` : "Each photo passes through four services."}
        </p>
      </div>

      {/* key replays the route for each new request. */}
      <div key={routeKey}
        className="mt-5 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)_2.5rem_minmax(0,1.5fr)_2.5rem_minmax(0,1fr)] md:items-start">
        <Stage name="gateway" role="Checks the upload, then calls each service in turn." ms={gatewayMs}
          lit={lit} at={STAGE_AT[0]} />
        <Connector lit={lit} at={PACKET_AT[0]} />
        <Stage name="preprocess" role="Strips metadata and crops to 224 × 224." ms={t?.preprocessMs}
          lit={lit} at={STAGE_AT[1]} />
        <Connector lit={lit} at={PACKET_AT[1]} />
        <Stage name="inference" role="MobileNetV2 labels the image. One of several replicas answers."
          ms={t?.inferenceMs} lit={lit} at={STAGE_AT[2]}>
          {lanes.length > 0 ? (
            <ul className="mt-3 space-y-1" aria-label="Inference replicas">
              {lanes.map((lane) => {
                const isActive = lane.pod === active;
                return (
                  <li key={lane.pod} title={lane.pod}
                    className={`grid grid-cols-[5.5rem_minmax(0,1fr)_2rem] items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${
                      isActive ? "bg-focus/15 font-medium" : ""
                    }`}>
                    <span className="flex items-center gap-1.5 truncate">
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? "bg-focus" : "bg-muted/50"}`} />
                      <span className="truncate">
                        {podSuffix(lane.pod)}
                        {multiNode && lane.node && <span className="block text-xs font-normal text-muted">{lane.node}</span>}
                      </span>
                    </span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-line">
                      <span className={`block h-full rounded-full transition-[width] duration-700 ${isActive ? "bg-focus" : "bg-muted/60"}`}
                        style={{ width: `${(lane.count / max) * 100}%` }} />
                    </span>
                    <span className="text-right tabular-nums text-muted">{lane.count}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted">Replicas appear here after the first photo.</p>
          )}
          {lanes.length > 0 && (
            <p className="mt-2 text-xs leading-snug text-muted">
              Photos per replica, last {recent.length} uploads
              {hidden > 0 ? ` (${hidden} older replica${hidden === 1 ? "" : "s"} not shown)` : ""}.
            </p>
          )}
        </Stage>
        <Connector lit={lit} at={PACKET_AT[2]} />
        <Stage name="storage" role="Keeps the original, the 224 px copy and the result." ms={t?.storageMs}
          lit={lit} at={STAGE_AT[3]} />
      </div>
    </section>
  );
}
