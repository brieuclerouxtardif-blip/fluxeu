// Analytics panel (M6, PLAN §4.6). Reads the durable DuckDB store via
// /api/analytics/* + /api/prices — so, unlike the M5 panels, it spans far past
// the 48 h scrubber window (as much history as has accumulated). Three views over
// a chosen window + zone set: multi-zone price comparison, a price duration
// curve, and a zonal price correlation matrix; plus CSV export. Correlations are
// computed server-side in DuckDB (SQL corr()); this only renders them.

import { useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import {
  exportCsvUrl,
  fetchCorrelation,
  fetchCoverage,
  fetchDuration,
  fetchPriceSeries,
} from "../api/client";
import type {
  CorrelationMatrix,
  Coverage,
  DurationCurve,
  PriceSeriesResponse,
} from "../types";

const WINDOWS = [
  { label: "24 h", hours: 24 },
  { label: "7 j", hours: 168 },
  { label: "30 j", hours: 720 },
] as const;

const PREFERRED = ["FR", "DE-LU", "BE", "NL", "ES", "IT-NORD"];
const MAX_ZONES = 6;
const PALETTE = ["#3DE0E0", "#fbbf24", "#a78bfa", "#34d399", "#f472b6", "#60a5fa"];

const dayFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
});
const spanFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function compareOption(resp: PriceSeriesResponse): EChartsOption {
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 10, top: 28, bottom: 4, containLabel: true },
    legend: {
      type: "scroll",
      top: 0,
      textStyle: { color: "#cbd5e1", fontSize: 10, fontFamily: "monospace" },
      itemWidth: 14,
      itemHeight: 8,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      valueFormatter: (v) => (v == null ? "n/a" : `${(v as number).toFixed(1)} €`),
    },
    xAxis: {
      type: "time",
      axisLabel: {
        color: "#64748b",
        fontSize: 10,
        formatter: (v: number) => dayFmt.format(new Date(v)),
      },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#64748b", fontSize: 10, formatter: "{value}" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    series: resp.zones.map((z, i) => ({
      name: z.zone,
      type: "line",
      showSymbol: false,
      step: "end", // day-ahead price is piecewise-constant per MTU
      lineStyle: { color: PALETTE[i % PALETTE.length], width: 1.3 },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      data: z.points.map((p) => [new Date(p.ts).getTime(), p.value]),
    })),
  };
}

function durationOption(dc: DurationCurve): EChartsOption {
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 10, top: 14, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: unknown) => {
        const arr = p as { data: [number, number] }[];
        const [pct, v] = arr[0].data;
        return `${pct.toFixed(0)}% du temps ≥<br/><b>${v.toFixed(1)} €/MWh</b>`;
      },
    },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: "#64748b", fontSize: 10, formatter: "{value}%" },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    series: [
      {
        type: "line",
        showSymbol: false,
        lineStyle: { color: "#3DE0E0", width: 1.5 },
        areaStyle: { color: "rgba(61,224,224,0.10)" },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "rgba(148,163,184,0.4)", type: "dashed" },
          data: [{ yAxis: 0 }], // zero line — negative prices read distinctly
        },
        data: dc.points.map((p) => [p.pct, p.eur_mwh]),
      },
    ],
  };
}

function correlationOption(cm: CorrelationMatrix): EChartsOption {
  const data: [number, number, number][] = [];
  cm.matrix.forEach((row, i) =>
    row.forEach((v, j) => {
      if (v != null) data.push([j, i, v]);
    }),
  );
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 8, top: 6, bottom: 4, containLabel: true },
    tooltip: {
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { data: [number, number, number] };
        return `${cm.zones[d.data[1]]} · ${cm.zones[d.data[0]]}<br/>ρ = <b>${d.data[2].toFixed(2)}</b>`;
      },
    },
    xAxis: {
      type: "category",
      data: cm.zones,
      axisLabel: { color: "#cbd5e1", fontSize: 9, fontFamily: "monospace", rotate: 45 },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
      axisTick: { show: false },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: cm.zones,
      axisLabel: { color: "#cbd5e1", fontSize: 9, fontFamily: "monospace" },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
      axisTick: { show: false },
      splitArea: { show: true },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemWidth: 10,
      itemHeight: 80,
      show: false,
      // diverging, colourblind-safe (indigo ↔ slate ↔ amber, no red/green)
      inRange: { color: ["#6366f1", "#334155", "#fbbf24"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          color: "#0b0e14",
          fontSize: 9,
          fontFamily: "monospace",
          formatter: (p: unknown) =>
            ((p as { data: [number, number, number] }).data[2]).toFixed(2),
        },
        itemStyle: { borderColor: "rgba(11,14,20,0.6)", borderWidth: 1 },
      },
    ],
  };
}

function ExportLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      download
      className="rounded-lg border border-white/10 bg-surface-2/60 px-3 py-2 font-mono text-[11px] text-slate-300 transition-colors hover:border-accent/40 hover:text-accent"
    >
      {children}
    </a>
  );
}

export default function AnalyticsPanel() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [hours, setHours] = useState<number>(168);
  const [selected, setSelected] = useState<string[]>([]);
  const [prices, setPrices] = useState<PriceSeriesResponse | null>(null);
  const [duration, setDuration] = useState<DurationCurve | null>(null);
  const [corr, setCorr] = useState<CorrelationMatrix | null>(null);
  const [error, setError] = useState(false);
  const reqId = useRef(0);

  // coverage once — also seeds the default zone selection
  useEffect(() => {
    fetchCoverage()
      .then((c) => {
        setCoverage(c);
        const avail = new Set(c.zones);
        const pick = PREFERRED.filter((z) => avail.has(z)).slice(0, 3);
        const seed = pick.length ? pick : c.zones.slice(0, 3);
        setSelected(seed);
      })
      .catch(() => setError(true));
  }, []);

  // refetch the three views whenever the window or zone set changes
  useEffect(() => {
    if (selected.length === 0) {
      setPrices(null);
      setDuration(null);
      setCorr(null);
      return;
    }
    const id = ++reqId.current;
    const apply = <T,>(setter: (v: T) => void) => (v: T) => {
      if (id === reqId.current) setter(v);
    };
    fetchPriceSeries(selected, hours).then(apply(setPrices)).catch(() => {});
    fetchDuration(selected[0], hours).then(apply(setDuration)).catch(() => {});
    if (selected.length >= 2) {
      fetchCorrelation(selected, hours).then(apply(setCorr)).catch(() => {});
    } else {
      setCorr(null);
    }
  }, [selected, hours]);

  const toggle = (z: string) =>
    setSelected((cur) =>
      cur.includes(z)
        ? cur.filter((x) => x !== z)
        : cur.length >= MAX_ZONES
          ? cur
          : [...cur, z],
    );

  const compare = useMemo(() => (prices ? compareOption(prices) : null), [prices]);
  const durOpt = useMemo(() => (duration ? durationOption(duration) : null), [duration]);
  const corrOpt = useMemo(() => (corr && corr.zones.length >= 2 ? correlationOption(corr) : null), [corr]);

  if (error) {
    return <p className="font-mono text-xs text-amber-300">analytics indisponible.</p>;
  }
  if (!coverage) {
    return <p className="font-mono text-xs text-amber-300">chargement…</p>;
  }

  const span =
    coverage.start && coverage.end
      ? `${spanFmt.format(new Date(coverage.start))} → ${spanFmt.format(new Date(coverage.end))}`
      : "—";
  const empty = coverage.price_rows === 0;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Historique accumulé
          </span>
          <span className="font-mono text-[10px] text-slate-400">
            {coverage.source} · {coverage.price_rows.toLocaleString("fr-FR")} pts
          </span>
        </div>
        <div className="font-mono text-[11px] text-slate-300">{span}</div>
      </div>

      {empty && (
        <p className="rounded-lg border border-amber-400/30 bg-surface-2/40 px-3 py-2 text-[11px] text-amber-300">
          ◌ La base DuckDB se remplit à chaque sweep (~60 min). Les courbes
          s'enrichiront avec le temps ; au-delà de 48 h une fois plusieurs sweeps
          accumulés.
        </p>
      )}

      {/* window selector */}
      <div className="flex overflow-hidden rounded-lg border border-white/10 bg-surface-1/60 font-mono text-xs">
        {WINDOWS.map((w) => (
          <button
            key={w.hours}
            onClick={() => setHours(w.hours)}
            className={`flex-1 px-3 py-2 transition-colors ${
              hours === w.hours ? "bg-accent/20 text-accent" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {/* zone multiselect */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="font-mono text-xs text-slate-300">Zones</span>
          <span className="text-[10px] text-slate-500">{selected.length}/{MAX_ZONES}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {coverage.zones.map((z) => {
            const on = selected.includes(z);
            const i = selected.indexOf(z);
            return (
              <button
                key={z}
                onClick={() => toggle(z)}
                className={`rounded border px-2 py-1 font-mono text-[10px] transition-colors ${
                  on
                    ? "border-accent/40 bg-accent/15 text-accent"
                    : "border-white/10 bg-surface-2/40 text-slate-400 hover:text-slate-200"
                }`}
                style={on ? { borderColor: PALETTE[i % PALETTE.length], color: PALETTE[i % PALETTE.length] } : undefined}
              >
                {z}
              </button>
            );
          })}
        </div>
      </div>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">Comparaison des prix</h3>
        <p className="mb-2 text-[10px] text-slate-500">
          palier par MTU · fenêtre {WINDOWS.find((w) => w.hours === hours)?.label}
        </p>
        {compare ? (
          <Chart option={compare} style={{ height: 200 }} />
        ) : (
          <p className="text-[11px] text-slate-500">sélectionne au moins une zone.</p>
        )}
      </section>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">
          Monotone de prix {selected[0] ? `— ${selected[0]}` : ""}
        </h3>
        <p className="mb-2 text-[10px] text-slate-500">
          % du temps où le prix dépasse un niveau · ligne 0 = prix négatifs
        </p>
        {durOpt && duration && duration.n > 0 ? (
          <Chart option={durOpt} style={{ height: 170 }} />
        ) : (
          <p className="text-[11px] text-slate-500">pas encore de données sur la fenêtre.</p>
        )}
      </section>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">Corrélation des prix</h3>
        <p className="mb-2 text-[10px] text-slate-500">
          Pearson sur pas alignés (SQL DuckDB){corr ? ` · ${corr.n_timestamps} pas` : ""}
        </p>
        {corrOpt ? (
          <Chart option={corrOpt} style={{ height: Math.max(140, (corr?.zones.length ?? 0) * 34 + 40) }} />
        ) : (
          <p className="text-[11px] text-slate-500">sélectionne au moins deux zones.</p>
        )}
      </section>

      <section className="border-t border-white/10 pt-3">
        <h3 className="mb-2 font-mono text-xs text-slate-300">Export CSV</h3>
        <div className="flex flex-wrap gap-2">
          <ExportLink href={exportCsvUrl("prices", hours, selected)}>↓ Prix (zones)</ExportLink>
          <ExportLink href={exportCsvUrl("prices", hours)}>↓ Prix (tout)</ExportLink>
          <ExportLink href={exportCsvUrl("flows", hours, selected)}>↓ Flux (zones)</ExportLink>
        </div>
      </section>
    </div>
  );
}
