import { useEffect, useState } from "react";
import MapView from "./map/MapView";
import { fetchHealth, type Health } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <MapView />

      <header className="pointer-events-none absolute left-4 top-4 z-10 flex items-center gap-3">
        <div className="rounded-lg border border-white/10 bg-surface-1/80 px-4 py-2 backdrop-blur">
          <h1 className="font-mono text-lg font-semibold tracking-tight text-accent">
            FluxEU
          </h1>
          <p className="text-xs text-slate-400">
            European electricity — prices &amp; cross-border flows
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-surface-1/80 px-3 py-2 font-mono text-xs backdrop-blur">
          {health ? (
            <span className="text-emerald-400">
              ● API {health.status} · {health.source}
            </span>
          ) : (
            <span className="text-amber-400">○ API offline</span>
          )}
        </div>
      </header>
    </div>
  );
}
