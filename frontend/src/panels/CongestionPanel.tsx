// Congestion panel (M5, PLAN §4.2): price-spread leaderboard + 48 h market
// convergence. Reads /api/metrics/* (derived in memory from the same cached
// snapshot/history as the map — zero extra API calls). Spreads are zone-level
// (incl. intra-country splits); rent is shown only where it is attributable.

import { useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import { fetchCongestion, fetchConvergence } from "../api/client";
import type { BorderMetric, CongestionSnapshot, ConvergenceSeries } from "../types";

const REFRESH_MS = 5 * 60 * 1000;
const WARMING_MS = 15 * 1000;
const TOP_N = 12;

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const hourFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  hour: "2-digit",
  minute: "2-digit",
});

// spread magnitude -> teal (coupled) ... amber ... red (congested)
const spreadColor = (s: number): string => {
  const t = Math.max(0, Math.min(1, s / 80));
  return `hsl(${Math.round(170 - 170 * t)}, 75%, 55%)`;
};

const label = (b: BorderMetric): string =>
  `${b.from_zone}–${b.to_zone}${b.internal ? " ⟲" : ""}`;

function leaderboardOption(borders: BorderMetric[]): EChartsOption {
  // echarts category axis runs bottom→top, so reverse to put the biggest on top
  const top = borders.slice(0, TOP_N).reverse();
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 48, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: { color: "#64748b", fontSize: 10, formatter: "{value}" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    yAxis: {
      type: "category",
      data: top.map(label),
      axisLabel: { color: "#cbd5e1", fontSize: 10, fontFamily: "monospace" },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
      axisTick: { show: false },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: unknown) => {
        const b = (p as { data: { border: BorderMetric } }).data.border;
        const lines = [
          `<b>${b.from_zone} – ${b.to_zone}</b>${b.internal ? " (intra-pays)" : ""}`,
          `spread : <b>${b.spread_eur_mwh.toFixed(2)} €/MWh</b>`,
          `${b.from_zone} ${b.price_from?.toFixed(2) ?? "n/a"} · ${b.to_zone} ${b.price_to?.toFixed(2) ?? "n/a"} €/MWh`,
          b.congestion_income_eur_h != null
            ? `rente : ~${Math.round(b.congestion_income_eur_h).toLocaleString("fr-FR")} €/h`
            : b.internal
              ? "rente : n/a (congestion interne)"
              : "rente : n/a (flux non attribuable)",
          b.capacity_regime === "FLOW_BASED" ? "frontière flow-based" : "frontière NTC",
        ];
        return lines.join("<br/>");
      },
    },
    series: [
      {
        type: "bar",
        data: top.map((b) => ({
          value: b.spread_eur_mwh,
          border: b,
          itemStyle: { color: spreadColor(b.spread_eur_mwh), borderRadius: 2 },
        })),
        barWidth: "62%",
        label: {
          show: true,
          position: "right",
          color: "#94a3b8",
          fontSize: 10,
          formatter: (p: unknown) =>
            (p as { value: number }).value.toFixed(0),
        },
      },
    ],
  };
}

function convergenceOption(cs: ConvergenceSeries): EChartsOption {
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 12, top: 14, bottom: 4, containLabel: true },
    xAxis: {
      type: "time",
      axisLabel: {
        color: "#64748b",
        fontSize: 10,
        formatter: (v: number) => hourFmt.format(new Date(v)),
      },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      interval: 25,
      axisLabel: { color: "#64748b", fontSize: 10, formatter: "{value}%" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: unknown) => {
        const arr = p as { data: [number, number] }[];
        const [t, v] = arr[0].data;
        return `${tsFmt.format(new Date(t))}<br/>couplé : <b>${v.toFixed(0)}%</b>`;
      },
    },
    series: [
      {
        type: "line",
        showSymbol: false,
        smooth: false,
        step: "end",
        lineStyle: { color: "#3DE0E0", width: 1.5 },
        areaStyle: { color: "rgba(61,224,224,0.13)" },
        data: cs.points.map((pt) => [new Date(pt.ts).getTime(), pt.converged_pct]),
      },
    ],
  };
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="font-mono text-base font-semibold text-slate-100">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

export default function CongestionPanel() {
  const [cong, setCong] = useState<CongestionSnapshot | null>(null);
  const [conv, setConv] = useState<ConvergenceSeries | null>(null);
  const [warming, setWarming] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [c, v] = await Promise.all([fetchCongestion(), fetchConvergence()]);
        if (cancelled) return;
        setCong(c);
        setConv(v);
        setWarming(false);
        timer.current = window.setTimeout(poll, REFRESH_MS);
      } catch {
        if (cancelled) return;
        setWarming(true);
        timer.current = window.setTimeout(poll, WARMING_MS);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  const leaderboard = useMemo(
    () => (cong ? leaderboardOption(cong.borders) : null),
    [cong],
  );
  const convergence = useMemo(
    () => (conv ? convergenceOption(conv) : null),
    [conv],
  );

  if (!cong || !conv) {
    return (
      <p className="font-mono text-xs text-amber-300">
        {warming ? "◌ métriques en préparation…" : "chargement…"}
      </p>
    );
  }

  const maxSpread = cong.borders[0]?.spread_eur_mwh ?? 0;
  const dataTs = cong.data_ts ? tsFmt.format(new Date(cong.data_ts)) : "—";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Frontières" value={String(cong.borders.length)} sub="avec prix des 2 zones" />
        <Stat label="Spread max" value={`${maxSpread.toFixed(0)} €`} sub="€/MWh, instant" />
        <Stat
          label="Couplage 48 h"
          value={`${conv.mean_converged_pct.toFixed(0)}%`}
          sub={`spread < ${conv.threshold_eur_mwh} €/MWh`}
        />
        <Stat
          label="Dispersion"
          value={`${conv.latest_std?.toFixed(0) ?? "—"} €`}
          sub="σ des prix, actuel"
        />
      </div>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">
          Frontières les plus congestionnées
        </h3>
        <p className="mb-2 text-[10px] text-slate-500">
          |Δ prix| par frontière · ⟲ = congestion interne · données {dataTs}
        </p>
        {leaderboard && <Chart option={leaderboard} style={{ height: 320 }} />}
      </section>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">
          Convergence du marché — 48 h
        </h3>
        <p className="mb-2 text-[10px] text-slate-500">
          % des frontières couplées (spread &lt; {conv.threshold_eur_mwh} €/MWh) par pas de marché
        </p>
        {convergence && <Chart option={convergence} style={{ height: 150 }} />}
      </section>
    </div>
  );
}
