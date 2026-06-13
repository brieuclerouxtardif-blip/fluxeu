import { useEffect, useMemo, useRef, useState } from "react";
import MapView, { type FlowMode } from "./map/MapView";
import TimeScrubber from "./map/TimeScrubber";
import PanelDock from "./panels/PanelDock";
import CongestionPanel from "./panels/CongestionPanel";
import SankeyPanel from "./panels/SankeyPanel";
import { priceRampCss } from "./map/priceColor";
import {
  fetchHealth,
  fetchHistory,
  fetchInterconnectors,
  fetchLiveSnapshot,
  fetchZones,
  fetchZonesGeoJSON,
  type Health,
} from "./api/client";
import type {
  Interconnector,
  LiveSnapshot,
  SnapshotHistory,
  Zone,
  ZonesGeoJSON,
} from "./types";

const POLL_OK_MS = 5 * 60 * 1000; // backend refreshes every ~60 min
const POLL_WARMING_MS = 15 * 1000; // snapshot/history warming up (cold start)
const HISTORY_REFRESH_MS = 30 * 60 * 1000;

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
  const [history, setHistory] = useState<SnapshotHistory | null>(null);
  const [scrubIndex, setScrubIndex] = useState<number | null>(null); // null = live
  const [warming, setWarming] = useState(false);
  const [mode, setMode] = useState<FlowMode>("commercial");
  const [panel, setPanel] = useState<"none" | "congestion" | "sankey">("none");

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

  // Load the 48 h history window (one GET); retry while warming, then refresh
  // off the backend cadence. The scrubber replays this window client-side.
  const histTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const h = await fetchHistory();
        if (cancelled) return;
        setHistory(h);
        histTimer.current = window.setTimeout(load, HISTORY_REFRESH_MS);
      } catch {
        if (cancelled) return;
        histTimer.current = window.setTimeout(load, POLL_WARMING_MS);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (histTimer.current) window.clearTimeout(histTimer.current);
    };
  }, []);

  // What the map shows: the live snapshot, or a replayed history frame.
  // Memoised so the synthesized snapshot keeps a stable identity between
  // renders (MapView only rebuilds layers when the frame actually changes).
  const displaySnapshot = useMemo<LiveSnapshot | null>(() => {
    if (scrubIndex != null && history && history.frames[scrubIndex]) {
      const f = history.frames[scrubIndex];
      return {
        ts: history.ts,
        source: history.source,
        data_ts: f.ts,
        granularity: history.granularity,
        prices: f.prices,
        nodes: history.nodes,
        edges: f.edges,
        net_positions: f.net_positions,
      };
    }
    return snapshot;
  }, [snapshot, history, scrubIndex]);

  const scrubbing = scrubIndex != null;
  const priceCount = displaySnapshot ? Object.keys(displaySnapshot.prices).length : 0;
  const arcCount = displaySnapshot
    ? displaySnapshot.edges.filter((e) =>
        mode === "commercial" ? e.commercial_mw != null : e.physical_mw != null,
      ).length
    : 0;
  const shownTs = displaySnapshot?.data_ts ? new Date(displaySnapshot.data_ts) : null;

  const PANEL_META = {
    congestion: {
      title: "Congestion & convergence",
      subtitle: "spreads de prix · couplage 48 h",
    },
    sankey: {
      title: "Flux nets — Sankey",
      subtitle: "échanges commerciaux · exporteur → importateur",
    },
  } as const;

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <MapView
        zones={zones}
        borders={borders}
        geojson={geojson}
        snapshot={displaySnapshot}
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
        {shownTs && (
          <div
            className={`rounded-lg border px-3 py-2 font-mono text-xs backdrop-blur ${
              scrubbing
                ? "border-accent/40 bg-surface-1/80 text-accent"
                : "border-white/10 bg-surface-1/80 text-slate-300"
            }`}
          >
            {scrubbing ? "rejeu " : "data "}
            {brussels.format(shownTs)} · {priceCount} prices · {arcCount} flows
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

      {/* 48 h time scrubber */}
      {history && history.frames.length > 0 && (
        <TimeScrubber
          frames={history.frames}
          live={!scrubbing}
          onScrub={(i) => setScrubIndex(i)}
          onLive={() => setScrubIndex(null)}
          format={(d) => brussels.format(d)}
        />
      )}

      {/* panel launchers (right edge) — hidden while a panel is open */}
      {panel === "none" && (
        <div className="absolute right-0 top-1/2 z-10 flex -translate-y-1/2 flex-col gap-2">
          <button
            onClick={() => setPanel("congestion")}
            className="rounded-l-lg border border-r-0 border-white/10 bg-surface-1/85 px-3 py-3 font-mono text-xs text-slate-300 backdrop-blur transition-colors hover:text-accent"
            title="Congestion & convergence"
          >
            ⟂ Congestion
          </button>
          <button
            onClick={() => setPanel("sankey")}
            className="rounded-l-lg border border-r-0 border-white/10 bg-surface-1/85 px-3 py-3 font-mono text-xs text-slate-300 backdrop-blur transition-colors hover:text-accent"
            title="Flux nets (Sankey)"
          >
            ⇄ Flux
          </button>
        </div>
      )}

      <PanelDock
        open={panel !== "none"}
        title={panel !== "none" ? PANEL_META[panel].title : ""}
        subtitle={panel !== "none" ? PANEL_META[panel].subtitle : undefined}
        onClose={() => setPanel("none")}
      >
        {panel === "congestion" && <CongestionPanel />}
        {panel === "sankey" && <SankeyPanel />}
      </PanelDock>
    </div>
  );
}
