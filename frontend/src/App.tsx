import { useEffect, useState } from "react";
import MapView from "./map/MapView";
import {
  fetchHealth,
  fetchInterconnectors,
  fetchZones,
  fetchZonesGeoJSON,
  type Health,
} from "./api/client";
import type { Interconnector, Zone, ZonesGeoJSON } from "./types";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [borders, setBorders] = useState<Interconnector[]>([]);
  const [geojson, setGeojson] = useState<ZonesGeoJSON | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    fetchZones().then(setZones).catch(console.error);
    fetchInterconnectors().then(setBorders).catch(console.error);
    fetchZonesGeoJSON().then(setGeojson).catch(console.error);
  }, []);

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <MapView zones={zones} borders={borders} geojson={geojson} />

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
        {zones.length > 0 && (
          <div className="rounded-lg border border-white/10 bg-surface-1/80 px-3 py-2 font-mono text-xs text-slate-300 backdrop-blur">
            {zones.length} zones · {borders.length} borders
          </div>
        )}
      </header>
    </div>
  );
}
