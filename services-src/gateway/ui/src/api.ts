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

export async function listResults(limit = 50): Promise<Result[]> {
  const res = await fetch(`/api/v1/results?limit=${limit}`);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, body);
  return (body as { results: Result[] }).results;
}

export function imageUrl(imageId: string, variant: "original" | "processed"): string {
  return `/api/v1/images/${encodeURIComponent(imageId)}?variant=${variant}`;
}

/** "inference-67b86b486c-kjntc" -> "kjntc": the part that tells replicas apart. */
export function podSuffix(pod?: string): string {
  if (!pod) return "unknown";
  return pod.split("-").pop() ?? pod;
}
