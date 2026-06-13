// Zone dashboard (M5, PLAN §4.4). Free, instant data only: 48 h price curve
// (from history), current price + country net position, and country-level
// exchanges with neighbours (from the live snapshot). The generation mix is
// deferred to M6 — fetching /public_power per country on demand would hit the
// SAME rate-limited Energy-Charts bucket as the background sweep and risk a 429
// that poisons the live data. Zone selected via dropdown.

import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import { priceColor } from "../map/priceColor";
import type { LiveSnapshot, SnapshotHistory, Zone } from "../types";

interface Props {
  zones: Zone[];
  history: SnapshotHistory | null;
  snapshot: LiveSnapshot | null;
}

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  hour: "2-digit",
  minute: "2-digit",
});
const mw = (v: number) => `${Math.round(v).toLocaleString("fr-FR")} MW`;
const rgb = (c: number[]) => `rgb(${c[0]},${c[1]},${c[2]})`;

function priceOption(pts: [number, number | null][]): EChartsOption {
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 8, top: 14, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      valueFormatter: (v) => (v == null ? "n/a" : `${(v as number).toFixed(2)} €/MWh`),
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
      axisLabel: { color: "#64748b", fontSize: 10, formatter: "{value}" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    series: [
      {
        type: "line",
        showSymbol: false,
        step: "end", // day-ahead price is piecewise-constant per MTU
        lineStyle: { color: "#3DE0E0", width: 1.5 },
        areaStyle: { color: "rgba(61,224,224,0.10)" },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "rgba(148,163,184,0.4)", type: "dashed" },
          data: [{ yAxis: 0 }], // zero line — negative prices read distinctly
        },
        data: pts,
      },
    ],
  };
}

function neighboursOption(
  items: { cc: string; value: number }[],
): EChartsOption {
  const top = items.slice(0, 10).reverse();
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 48, top: 6, bottom: 4, containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: { color: "#64748b", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
    },
    yAxis: {
      type: "category",
      data: top.map((d) => d.cc),
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
        const d = p as { name: string; value: number };
        const verb = d.value >= 0 ? "import depuis" : "export vers";
        return `${verb} ${d.name}<br/><b>${mw(Math.abs(d.value))}</b>`;
      },
    },
    series: [
      {
        type: "bar",
        data: top.map((d) => ({
          value: d.value,
          itemStyle: { color: d.value >= 0 ? "#fbbf24" : "#2dd4bf", borderRadius: 2 },
        })),
        barWidth: "60%",
        label: {
          show: true,
          position: "right",
          color: "#94a3b8",
          fontSize: 10,
          formatter: (p: unknown) => mw(Math.abs((p as { value: number }).value)),
        },
      },
    ],
  };
}

export default function ZonePanel({ zones, history, snapshot }: Props) {
  const sorted = useMemo(
    () => [...zones].sort((a, b) => a.key.localeCompare(b.key)),
    [zones],
  );
  const [key, setKey] = useState<string>("");

  // default to a priced zone (FR if present) once data arrives
  useEffect(() => {
    if (key || !snapshot) return;
    const fr = sorted.find((z) => z.key === "FR" && snapshot.prices[z.key] != null);
    const first = fr ?? sorted.find((z) => snapshot.prices[z.key] != null) ?? sorted[0];
    if (first) setKey(first.key);
  }, [snapshot, sorted, key]);

  const zone = sorted.find((z) => z.key === key) ?? null;
  const cc = useMemo(() => {
    const node = (snapshot?.nodes ?? history?.nodes ?? []).find((n) =>
      n.zones.includes(key),
    );
    return node?.code ?? null;
  }, [snapshot, history, key]);

  const priceSeries = useMemo<[number, number | null][]>(() => {
    if (!history) return [];
    return history.frames.map((f) => [
      new Date(f.ts).getTime(),
      f.prices[key] ?? null,
    ]);
  }, [history, key]);

  // country-level exchanges with neighbours, from the zone's country perspective
  const neighbours = useMemo(() => {
    if (!snapshot || !cc) return [];
    const out: { cc: string; value: number }[] = [];
    for (const e of snapshot.edges) {
      if (e.commercial_mw == null) continue;
      if (e.from_zone === cc)
        out.push({ cc: e.to_zone, value: -e.commercial_mw }); // from cc -> export
      else if (e.to_zone === cc)
        out.push({ cc: e.from_zone, value: e.commercial_mw }); // into cc -> import
    }
    return out.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  }, [snapshot, cc]);

  const price = zone && snapshot ? snapshot.prices[zone.key] : undefined;
  const net = cc && snapshot ? snapshot.net_positions[cc] : undefined;

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
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Prix actuel</div>
          <div className="flex items-center gap-2">
            {price != null && (
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ background: rgb(priceColor(price)) }}
              />
            )}
            <span className="font-mono text-base font-semibold text-slate-100">
              {price != null ? `${price.toFixed(1)} €` : "—"}
            </span>
          </div>
          <div className="text-[10px] text-slate-500">
            €/MWh{price != null && price < 0 ? " · négatif" : ""}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            Position nette {cc ? `(${cc})` : ""}
          </div>
          <div className="font-mono text-base font-semibold text-slate-100">
            {net != null ? mw(Math.abs(net)) : "—"}
          </div>
          <div className="text-[10px] text-slate-500">
            {net == null ? "niveau pays" : net >= 0 ? "importateur net" : "exportateur net"}
          </div>
        </div>
      </div>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">Prix day-ahead — 48 h</h3>
        <p className="mb-2 text-[10px] text-slate-500">
          {zone ? `${zone.key} — ${zone.name}` : ""} · palier par MTU · ligne 0 = prix négatifs
        </p>
        {history ? (
          <Chart option={priceOption(priceSeries)} style={{ height: 170 }} />
        ) : (
          <p className="text-[11px] text-amber-300">◌ historique en préparation…</p>
        )}
      </section>

      <section>
        <h3 className="mb-1 font-mono text-xs text-slate-300">
          Échanges avec les voisins
        </h3>
        <p className="mb-2 text-[10px] text-slate-500">
          niveau pays {cc ? `(${cc})` : ""} · <span className="text-amber-300">import +</span> ·{" "}
          <span className="text-teal-300">export −</span>
        </p>
        {neighbours.length > 0 ? (
          <Chart option={neighboursOption(neighbours)} style={{ height: Math.max(90, neighbours.slice(0, 10).length * 26) }} />
        ) : (
          <p className="text-[11px] text-slate-500">pas de flux transfrontalier pour ce pays.</p>
        )}
      </section>

      <p className="border-t border-white/10 pt-3 text-[10px] text-slate-600">
        Mix de production par filière : <span className="text-slate-400">M6</span> — éviter de
        saturer l'API Energy-Charts (même quota que le snapshot live) ; viendra d'ENTSO-E.
      </p>
    </div>
  );
}
