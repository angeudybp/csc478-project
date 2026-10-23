import { useEffect, useRef, useState } from "react";
import { ApiError, MAX_UPLOAD_BYTES, uploadImage, type Result } from "../api";

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; progress: number }
  | { phase: "done"; name: string; totalMs: number }
  | { phase: "error"; message: string; detail?: string };

const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(1);

export default function UploadPanel({ onUploaded }: { onUploaded: (r: Result) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  async function handle(file?: File) {
    if (!file) return;
    // Only the size is checked here, to avoid sending 8 MB+ for nothing. File type is left to the
    // gateway, so its 415 validation is what the user sees.
    if (file.size > MAX_UPLOAD_BYTES) {
      setState({ phase: "error", message: `${file.name} is ${mb(file.size)} MB. The limit is 8 MB.` });
      return;
    }
    setPreview(URL.createObjectURL(file));
    setState({ phase: "uploading", name: file.name, progress: 0 });
    try {
      const result = await uploadImage(file, (progress) =>
        setState((s) => (s.phase === "uploading" ? { ...s, progress } : s)));
      setState({ phase: "done", name: file.name, totalMs: result.timings.totalMs });
      onUploaded(result);
    } catch (e) {
      const err = e as ApiError;
      setPreview(null);
      setState({
        phase: "error",
        message: err.message,
        detail: [err.status ? `HTTP ${err.status}` : null, err.code, err.requestId && `request ${err.requestId}`]
          .filter(Boolean).join(", "),
      });
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  const busy = state.phase === "uploading";

  return (
    <section aria-labelledby="upload-heading">
      <h2 id="upload-heading" className="text-xl font-semibold tracking-tight">Classify an image</h2>
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (!busy) handle(e.dataTransfer.files[0]); }}
        className={`relative mt-4 flex aspect-[4/3] w-full flex-col items-center justify-center overflow-hidden rounded-md border-2 border-dashed text-center transition-colors ${
          dragging ? "border-marker bg-marker/10" : "border-rule bg-sheet hover:border-graphite"
        } ${busy ? "cursor-progress" : "cursor-pointer"}`}
      >
        {preview ? (
          <img src={preview} alt="" className="absolute inset-0 h-full w-full object-contain p-3" />
        ) : (
          <span className="px-6">
            <span className="block text-lg font-medium">Drop a JPEG or PNG here</span>
            <span className="mt-1 block text-sm text-graphite">or click to choose a file, up to 8 MB</span>
          </span>
        )}
        {busy && (
          <span className="absolute inset-x-0 bottom-0 h-1 bg-rule">
            <span className="block h-full bg-marker transition-[width]" style={{ width: `${state.progress * 100}%` }} />
          </span>
        )}
      </button>
      <input ref={input} type="file" accept="image/jpeg,image/png" className="sr-only" tabIndex={-1}
        onChange={(e) => handle(e.target.files?.[0])} />

      <div className="mt-3 min-h-12 text-sm" aria-live="polite">
        {state.phase === "uploading" && (
          <p className="text-graphite">
            {state.progress < 1 ? `Uploading ${state.name}, ${Math.round(state.progress * 100)}%` : `Classifying ${state.name}`}
          </p>
        )}
        {state.phase === "done" && (
          <p className="text-graphite">Classified {state.name} in {state.totalMs} ms. Drop another to compare.</p>
        )}
        {state.phase === "error" && (
          <div className="rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-alert" role="alert">
            <p className="font-medium">{state.message}</p>
            {state.detail && <p className="mt-0.5 text-xs opacity-80">{state.detail}</p>}
          </div>
        )}
      </div>
    </section>
  );
}
