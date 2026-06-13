import { useEffect, useRef, useState } from "react";
import MapView, { type FlowMode } from "./map/MapView";
import { priceRampCss } from "./map/priceColor";
import {
  fetchHealth,
  fetchInterconnectors,
  fetchLiveSnapshot,
  fetchZones,
  fetchZonesGeoJSON,
  type Health,
} from "./api/client";
import type { Interconnector, LiveSnapshot, Zone, ZonesGeoJSON } from "./types";

const POLL_OK_MS = 5 * 60 * 1000; // backend refreshes every 10 min
const POLL_WARMING_MS = 15 * 1000; // snapshot warming up (cold start)

const brussels = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [borders, setBorders] = useState<Interconnector[]>([]);
  const [geojson, setGeojson] = useState<ZonesGeoJSON | null>(null);
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [warming, setWarming] = useState(false);
  const [mode, setMode] = useState<FlowMode>("commercial");

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    fetchZones().then(setZones).catch(console.error);
    fetchInterconnectors().then(setBorders).catch(console.error);
    fetchZonesGeoJSON().then(setGeojson).catch(console.error);
  }, []);

  // Poll the live snapshot. While the backend is warming (503) retry quickly,
  // then settle into the slow cadence once data is flowing.
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await fetchLiveSnapshot();
        if (cancelled) return;
        setSnapshot(s);
        setWarming(false);
        timer.current = window.setTimeout(poll, POLL_OK_MS);
      } catch {
        if (cancelled) return;
        setWarming(true);
        timer.current = window.setTimeout(poll, POLL_WARMING_MS);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  const priceCount = snapshot ? Object.keys(snapshot.prices).length : 0;
  const arcCount = snapshot
    ? snapshot.edges.filter((e) =>
        mode === "commercial" ? e.commercial_mw != null : e.physical_mw != null,
      ).length
    : 0;
  const dataTs = snapshot?.data_ts ? new Date(snapshot.data_ts) : null;

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <MapView
        zones={zones}
        borders={borders}
        geojson={geojson}
        snapshot={snapshot}
        mode={mode}
      />

      {/* header */}
      <header className="pointer-events-none absolute left-4 top-4 z-10 flex flex-wrap items-center gap-3">
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
        {dataTs && (
          <div className="rounded-lg border border-white/10 bg-surface-1/80 px-3 py-2 font-mono text-xs text-slate-300 backdrop-blur">
            data {brussels.format(dataTs)} · {priceCount} prices · {arcCount} flows
          </div>
        )}
        {warming && !snapshot && (
          <div className="rounded-lg border border-amber-400/30 bg-surface-1/80 px-3 py-2 font-mono text-xs text-amber-300 backdrop-blur">
            ◌ live snapshot warming up…
          </div>
        )}
      </header>

      {/* commercial / physical toggle */}
      <div className="absolute right-4 top-20 z-10 flex overflow-hidden rounded-lg border border-white/10 bg-surface-1/80 font-mono text-xs backdrop-blur">
        {(["commercial", "physical"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-2 transition-colors ${
              mode === m
                ? "bg-accent/20 text-accent"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {m === "commercial" ? "Commercial" : "Physique"}
          </button>
        ))}
      </div>

      {/* legend */}
      <div className="absolute bottom-4 left-4 z-10 w-72 rounded-lg border border-white/10 bg-surface-1/80 px-4 py-3 font-mono text-xs text-slate-300 backdrop-blur">
        <div className="mb-1 text-slate-400">Prix day-ahead (€/MWh)</div>
        <div
          className="h-2 w-full rounded"
          style={{ background: priceRampCss() }}
        />
        <div className="mt-1 flex justify-between text-[10px] text-slate-500">
          <span>−100</span>
          <span>0</span>
          <span>80</span>
          <span>250</span>
          <span>600+</span>
        </div>
        <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
          <span className="inline-block h-0.5 w-8 rounded bg-gradient-to-r from-teal-400 to-sky-200" />
          <span>arc animé = sens du flux · épaisseur ∝ |MW|</span>
        </div>
        <div className="mt-1 text-[10px] text-slate-500">
          prix négatifs en bleu/indigo · flux niveau pays
        </div>
      </div>
    </div>
  );
}
