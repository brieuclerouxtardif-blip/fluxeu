// Modélisation panel (M7, PLAN §4.7). Overlays a forward price band (p10/p50/p90,
// seasonal-naive baseline from /api/model/forward) on the recent realized spot —
// the "modelled vs cleared" view. A placeholder for the real merit-order /
// peakero-forecaster model: same chart, richer curve when that's plugged in.

import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import { fetchForward } from "../api/client";
import type { ForwardCurve, Zone } from "../types";

const HORIZON = 24;

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
});
const fullFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function option(fc: ForwardCurve): EChartsOption {
  const t = (s: string) => new Date(s).getTime();
  const p10 = fc.forward.map((p) => [t(p.ts), p.p10]);
  const band = fc.forward.map((p) => [t(p.ts), Math.max(0, p.p90 - p.p10)]);
  const p50 = fc.forward.map((p) => [t(p.ts), p.p50]);
  const realized = fc.realized.map((r) => [t(r.ts), r.eur_mwh]);
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 10, top: 28, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      data: ["réalisé", "modèle p50"],
      textStyle: { color: "#cbd5e1", fontSize: 10, fontFamily: "monospace" },
      itemWidth: 16,
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
        formatter: (v: number) => tsFmt.format(new Date(v)),
      },
      axisLine: { lineStyle: { color: "rgba(148,163,184,0.25)" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    series: [
      // p10..p90 band via the stack trick (lower invisible base + visible width)
      {
        name: "p10",
        type: "line",
        data: p10,
        stack: "conf",
        symbol: "none",
        lineStyle: { width: 0 },
        areaStyle: { opacity: 0 },
        silent: true,
        z: 1,
      },
      {
        name: "p10–p90",
        type: "line",
        data: band,
        stack: "conf",
        symbol: "none",
        lineStyle: { width: 0 },
        areaStyle: { color: "rgba(167,139,250,0.18)" },
        silent: true,
        z: 1,
      },
      {
        name: "modèle p50",
        type: "line",
        data: p50,
        symbol: "none",
        lineStyle: { color: "#a78bfa", width: 1.5, type: "dashed" },
        z: 2,
      },
      {
        name: "réalisé",
        type: "line",
        data: realized,
        symbol: "none",
        step: "end", // day-ahead spot is piecewise-constant per MTU
        lineStyle: { color: "#3DE0E0", width: 1.5 },
        z: 3,
      },
    ],
  };
}

export default function ModelPanel({ zones }: { zones: Zone[] }) {
  const sorted = useMemo(
    () => [...zones].sort((a, b) => a.key.localeCompare(b.key)),
    [zones],
  );
  const [key, setKey] = useState("");
  const [fc, setFc] = useState<ForwardCurve | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!key && sorted.length) {
      const fr = sorted.find((z) => z.key === "FR");
      setKey((fr ?? sorted[0]).key);
    }
  }, [sorted, key]);

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    setLoading(true);
    fetchForward(key, HORIZON)
      .then((d) => !cancelled && (setFc(d), setLoading(false)))
      .catch(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [key]);

  const opt = useMemo(() => (fc && fc.forward.length ? option(fc) : null), [fc]);
  const generated = fc ? fullFmt.format(new Date(fc.generated_ts)) : "—";

  return (
    <div className="space-y-4">
      <select
        value={key}
        onChange={(e) => setKey(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-surface-2/60 px-3 py-2 font-mono text-xs text-slate-200 focus:border-accent/40 focus:outline-none"
      >
        {sorted.map((z) => (
          <option key={z.key} value={z.key} className="bg-surface-1">
            {z.key} — {z.name}
          </option>
        ))}
      </select>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Méthode</div>
          <div className="font-mono text-xs text-slate-200">seasonal-naive</div>
          <div className="text-[10px] text-slate-500">profil horaire (Bruxelles)</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Calé sur</div>
          <div className="font-mono text-xs text-slate-200">{fc?.n_history ?? 0} points</div>
          <div className="text-[10px] text-slate-500">généré {generated}</div>
        </div>
      </div>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">
          Forward modélisé vs spot réalisé — {key}
        </h3>
        <p className="mb-2 text-[10px] text-slate-500">
          bande <span className="text-violet-300">p10–p90</span> ·{" "}
          <span className="text-violet-300">p50 pointillé</span> = modèle ·{" "}
          <span className="text-teal-300">réalisé</span> = spot 48 h · horizon {HORIZON} h
        </p>
        {opt ? (
          <Chart option={opt} style={{ height: 220 }} />
        ) : (
          <p className="text-[11px] text-amber-300">
            {loading
              ? "◌ calcul du forward…"
              : "historique insuffisant — le modèle s'enrichit à chaque sweep."}
          </p>
        )}
      </section>

      <p className="border-t border-white/10 pt-3 text-[10px] text-slate-600">
        Baseline statistique (placeholder §4.7) — à remplacer par le simulateur
        merit-order / <span className="text-slate-400">peakero-forecaster</span> (forward
        probabiliste), même contrat d'overlay.
      </p>
    </div>
  );
}
