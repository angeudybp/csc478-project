import { useCallback, useEffect, useState } from "react";
import { listResults, type Result } from "./api";
import ContactSheet from "./components/ContactSheet";
import PipelineStrip from "./components/PipelineStrip";
import PredictionPanel from "./components/PredictionPanel";
import UploadPanel from "./components/UploadPanel";

export default function App() {
  const [current, setCurrent] = useState<Result | null>(null);
  const [recent, setRecent] = useState<Result[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [routeKey, setRouteKey] = useState(0);

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
  }, [refresh]);

  const show = (r: Result) => {
    setCurrent(r);
    setRouteKey((k) => k + 1);
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-6">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-rule pb-5">
        <h1 className="text-2xl font-semibold tracking-tight">KubeBalancer</h1>
        <p className="text-graphite">Image classification on Kubernetes. Upload a photo and follow it through the cluster.</p>
      </header>

      <main>
        <div className="mt-8 grid grid-cols-1 gap-10 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <UploadPanel onUploaded={(r) => { show(r); refresh(); }} />
          <PredictionPanel result={current} />
        </div>
        <PipelineStrip result={current} recent={recent} routeKey={routeKey} />
        <ContactSheet results={recent} selectedId={current?.imageId} error={recentError}
          onSelect={show} onRefresh={refresh} />
      </main>
    </div>
  );
}
