// Client for the gateway's public API (M1 report §4.1). Same origin, so no CORS.

export interface ScoredLabel {
  label: string;
  score: number;
}

export interface Result {
  imageId: string;
  label: string;
  confidence: number;
  topK: ScoredLabel[];
  modelVersion: string;
  mock: boolean;
  filename?: string;
  source?: "user" | "test"; // "test" = uploaded by scripts/smoke.sh or evidence.sh
  originalSize?: { width: number; height: number };
  servedBy?: { inferencePod?: string; inferenceNode?: string };
  timings: { preprocessMs: number; inferenceMs: number; storageMs: number; totalMs: number };
  createdAt: string;
  requestId: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId?: string,
  ) {
    super(message);
  }
}

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

function toApiError(status: number, body: unknown): ApiError {
  const b = (body ?? {}) as { error?: { code?: string; message?: string }; requestId?: string };
  if (status === 0) return new ApiError("The gateway could not be reached.", 0, "NETWORK");
  return new ApiError(b.error?.message ?? `Request failed with HTTP ${status}.`, status,
    b.error?.code ?? "HTTP_ERROR", b.requestId);
}

/** Upload with XMLHttpRequest rather than fetch, because only XHR reports upload progress. */
export function uploadImage(file: File, onProgress: (fraction: number) => void): Promise<Result> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    xhr.open("POST", "/api/v1/images");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status === 200 ? resolve(xhr.response as Result) : reject(toApiError(xhr.status, xhr.response));
    xhr.onerror = () => reject(toApiError(0, null));
    xhr.send(form);
  });
}

/** Recent uploads made by people. Uploads from the test scripts are left out. */
export async function listResults(limit = 50): Promise<Result[]> {
  const res = await fetch("/api/v1/results?limit=100"); // The API maximum; tests are filtered out below.
  const body = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, body);
  return (body as { results: Result[] }).results.filter((r) => r.source !== "test").slice(0, limit);
}

export function imageUrl(imageId: string, variant: "original" | "processed"): string {
  return `/api/v1/images/${encodeURIComponent(imageId)}?variant=${variant}`;
}

/** "inference-67b86b486c-kjntc" -> "kjntc": the part that tells replicas apart. */
export function podSuffix(pod?: string): string {
  if (!pod) return "unknown";
  return pod.split("-").pop() ?? pod;
}

export type Variant = "original" | "processed";

/** Same URL with download=1: the gateway answers with a filename built from the label. */
export function downloadUrl(imageId: string, variant: Variant): string {
  return `${imageUrl(imageId, variant)}&download=1`;
}

/** Mirrors the gateway's download_name(), so the UI can show the name a download will get. */
export function downloadName(r: Result, variant: Variant, ext = "jpg"): string {
  const slug = r.label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "image";
  const kind = variant === "original" ? "original" : "model-input-224px";
  return `${slug}-${r.imageId.slice(-6).toLowerCase()}-${kind}.${ext}`;
}

export const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
