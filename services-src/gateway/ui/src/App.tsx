import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, imageUrl, listResults, MAX_UPLOAD_BYTES, uploadImage, type Result } from "./api";
import Gallery from "./components/Gallery";
import { ApertureIcon } from "./components/icons";
import PipelineStrip from "./components/PipelineStrip";
import ResultPanel from "./components/ResultPanel";
import Stage, { type UploadState } from "./components/Stage";

const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(1);

export default function App() {
  const [current, setCurrent] = useState<Result | null>(null);
  const [recent, setRecent] = useState<Result[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [uploadPreview, setUploadPreview] = useState<string | null>(null);
  const [routeKey, setRouteKey] = useState(0);
  // Photos uploaded in this session are shown from memory instead of being downloaded again.
  const previews = useRef(new Map<string, string>());

  const refresh = useCallback(async () => {
    try {
      setRecent(await listResults(50));
      setRecentError(null);
    } catch (e) {
      setRecentError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const urls = previews.current;
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [refresh]);

  const show = (r: Result) => {
    setCurrent(r);
    setUpload({ phase: "idle" });
    setRouteKey((k) => k + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  async function classify(file: File) {
    // Only the size is checked here (to avoid sending 8 MB+ for nothing); the gateway decides
    // whether the file is a valid image, so its validation is what the user sees.
    if (file.size > MAX_UPLOAD_BYTES) {
      setUpload({ phase: "error", message: `${file.name} is ${mb(file.size)} MB. The limit is 8 MB.` });
      return;
    }
    const preview = URL.createObjectURL(file);
    setUploadPreview(preview);
    setUpload({ phase: "uploading", name: file.name, progress: 0 });
    try {
      const result = await uploadImage(file, (progress) =>
        setUpload((u) => (u.phase === "uploading" ? { ...u, progress } : u)));
      previews.current.set(result.imageId, preview);
      setUploadPreview(null);
      setUpload({ phase: "idle" });
      setCurrent(result);
      setRouteKey((k) => k + 1);
      refresh();
    } catch (e) {
      const err = e as ApiError;
      URL.revokeObjectURL(preview);
      setUploadPreview(null);
      setUpload({
        phase: "error",
        message: err.message,
        detail: [err.status ? `HTTP ${err.status}` : null, err.code, err.requestId && `request ${err.requestId}`]
          .filter(Boolean).join(", "),
      });
    }
  }

  const busy = upload.phase === "uploading";
  const src = busy
    ? uploadPreview
    : current
      ? previews.current.get(current.imageId) ?? imageUrl(current.imageId, "original")
      : null;

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 py-6">
        <a href="/" className="flex items-center gap-2.5 rounded-md">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-white shadow-soft">
            <ApertureIcon width={20} height={20} />
          </span>
          <span className="text-lg font-semibold tracking-tight">KubeBalancer</span>
        </a>
        <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted shadow-soft">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          MobileNetV2 on Kubernetes
        </span>
      </header>

      <main>
        <div className="mt-4 grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <Stage src={src} result={busy ? null : current} upload={upload} onFile={classify} />
          <ResultPanel result={current} busy={busy} />
        </div>
        <PipelineStrip result={busy ? null : current} recent={recent} routeKey={routeKey} />
        <Gallery results={recent} selectedId={current?.imageId} error={recentError}
          onSelect={show} onRefresh={refresh} />
      </main>
    </div>
  );
}
