// Interconnector explorer (M5, PLAN §4.3): searchable list of every modelled
// border + a per-border detail (commercial vs physical flow + price-spread
// overlay over 48 h). Entirely client-side — reuses the already-loaded
// interconnectors + 48 h history, no extra API calls. NTC / utilisation and the
// duration curve are gated to ENTSO-E (M6); demo mode shows measured flow only.

import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import type {
  FlowEdge,
  Interconnector,
  LiveSnapshot,
  SnapshotHistory,
} from "../types";

interface Props {
  borders: Interconnector[];
  history: SnapshotHistory | null;
  snapshot: LiveSnapshot | null;
}

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  hour: "2-digit",
  minute: "2-digit",
});
const mw = (v: number) => `${Math.round(v).toLocaleString("fr-FR")} MW`;
const gw = (v: number) => `${(v / 1000).toFixed(1)} GW`;

// zone key -> ISO-2 country, from the flow-graph nodes
function zoneCc(nodes: { code: string; zones: string[] }[]): Map<string, string> {
  const m = new Map<string, string>();
  nodes.forEach((n) => n.zones.forEach((z) => m.set(z, n.code)));
  return m;
}

// the country edge for a country pair, if present
function edgeFor(edges: FlowEdge[], a: string, b: string): FlowEdge | undefined {
  return edges.find(
    (e) =>
      (e.from_zone === a && e.to_zone === b) ||
      (e.from_zone === b && e.to_zone === a),
  );
}

// commercial flow oriented fz->tz (+) using a snapshot/frame's edges
function orientedCommercial(
  edges: FlowEdge[],
  ccFrom: string,
  ccTo: string,
): number | null {
  if (ccFrom === ccTo) return null; // intra-country border, no cross-border flow
  const e = edgeFor(edges, ccFrom, ccTo);
  if (!e || e.commercial_mw == null) return null;
  return e.from_zone === ccFrom ? e.commercial_mw : -e.commercial_mw;
}

function capacityMw(b: Interconnector): number {
  return b.cables.reduce((s, c) => s + (c.commissioned && c.mw ? c.mw : 0), 0);
}

function detailOption(
  fz: string,
  tz: string,
  pts: { t: number; commercial: number | null; physical: number | null; spread: number | null }[],
): EChartsOption {
  return {
    backgroundColor: "transparent",
    grid: { left: 4, right: 4, top: 28, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      textStyle: { color: "#94a3b8", fontSize: 10 },
      data: ["commercial", "physique", "spread"],
      itemWidth: 14,
      itemHeight: 8,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
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
    yAxis: [
      {
        type: "value",
        name: `MW  (+ = ${fz}→${tz})`,
        nameTextStyle: { color: "#64748b", fontSize: 9, align: "left" },
        axisLabel: { color: "#64748b", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
      },
      {
        type: "value",
        name: "spread €",
        nameTextStyle: { color: "#64748b", fontSize: 9, align: "right" },
        position: "right",
        axisLabel: { color: "#64748b", fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "commercial",
        type: "line",
        showSymbol: false,
        step: "end",
        lineStyle: { color: "#3DE0E0", width: 1.5 },
        data: pts.map((p) => [p.t, p.commercial]),
      },
      {
        name: "physique",
        type: "line",
        showSymbol: false,
        smooth: true,
        lineStyle: { color: "#fbbf24", width: 1.2 },
        data: pts.map((p) => [p.t, p.physical]),
      },
      {
        name: "spread",
        type: "line",
        yAxisIndex: 1,
        showSymbol: false,
        step: "end",
        lineStyle: { color: "#a78bfa", width: 1, type: "dashed" },
        areaStyle: { color: "rgba(167,139,250,0.08)" },
        data: pts.map((p) => [p.t, p.spread]),
      },
    ],
  };
}

export default function ExplorerPanel({ borders, history, snapshot }: Props) {
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<Interconnector | null>(null);

  const z2c = useMemo(
    () => zoneCc(snapshot?.nodes ?? history?.nodes ?? []),
    [snapshot, history],
  );

  // current commercial flow per border (oriented), for the list
  const rows = useMemo(() => {
    const edges = snapshot?.edges ?? [];
    const q = query.trim().toLowerCase();
    return borders
      .map((b) => {
        const flow = orientedCommercial(
          edges,
          z2c.get(b.from_zone) ?? b.from_zone,
          z2c.get(b.to_zone) ?? b.to_zone,
        );
        return { b, flow, cap: capacityMw(b) };
      })
      .filter(({ b }) => {
        if (!q) return true;
        const hay = `${b.from_zone} ${b.to_zone} ${b.cables.map((c) => c.name).join(" ")}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, z) => Math.abs(z.flow ?? 0) - Math.abs(a.flow ?? 0));
  }, [borders, snapshot, z2c, query]);

  // detail series over 48 h for the selected border
  const detail = useMemo(() => {
    if (!sel || !history) return null;
    const ccF = z2c.get(sel.from_zone) ?? sel.from_zone;
    const ccT = z2c.get(sel.to_zone) ?? sel.to_zone;
    const internal = ccF === ccT;
    const pts = history.frames.map((f) => {
      const t = new Date(f.ts).getTime();
      let commercial: number | null = null;
      let physical: number | null = null;
      if (!internal) {
        const e = edgeFor(f.edges, ccF, ccT);
        if (e) {
          const sign = e.from_zone === ccF ? 1 : -1;
          commercial = e.commercial_mw == null ? null : sign * e.commercial_mw;
          physical = e.physical_mw == null ? null : sign * e.physical_mw;
        }
      }
      const pf = f.prices[sel.from_zone];
      const pt = f.prices[sel.to_zone];
      const spread = pf != null && pt != null ? Math.abs(pf - pt) : null;
      return { t, commercial, physical, spread };
    });
    return { internal, pts };
  }, [sel, history, z2c]);

  if (sel) {
    const cap = capacityMw(sel);
    return (
      <div className="space-y-3">
        <button
          onClick={() => setSel(null)}
          className="font-mono text-[11px] text-slate-400 transition-colors hover:text-accent"
        >
          ← toutes les frontières
        </button>
        <div>
          <h3 className="font-mono text-sm font-semibold text-slate-100">
            {sel.from_zone} – {sel.to_zone}
          </h3>
          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-slate-300">
              {sel.capacity_regime === "FLOW_BASED" ? "flow-based" : "NTC"}
            </span>
            {sel.gb_decoupled && (
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300">
                GB découplé
              </span>
            )}
            {cap > 0 && (
              <span className="rounded bg-surface-2 px-1.5 py-0.5 text-slate-300">
                {gw(cap)} DC
              </span>
            )}
          </div>
        </div>

        {sel.cables.length > 0 && (
          <ul className="space-y-1 text-[11px] text-slate-400">
            {sel.cables.map((c) => (
              <li key={c.name} className="flex justify-between gap-2">
                <span className="text-slate-300">{c.name}</span>
                <span className="tabular-nums">
                  {c.mw ? mw(c.mw) : "—"} · {c.tech ?? "?"} · {c.year ?? "?"}
                  {!c.commissioned && " (à venir)"}
                </span>
              </li>
            ))}
          </ul>
        )}

        <section>
          <h4 className="mb-1 font-mono text-xs text-slate-300">
            Flux & spread — 48 h
          </h4>
          {detail?.internal ? (
            <p className="text-[11px] text-slate-500">
              Frontière intra-pays : pas de flux transfrontalier mesuré (le graphe de
              flux est au niveau pays). Spread de prix entre zones ci-dessous.
            </p>
          ) : (
            <p className="mb-2 text-[10px] text-slate-500">
              flux commercial (programmé) vs physique (mesuré) · spread = |Δ prix|
            </p>
          )}
          {detail && <Chart option={detailOption(sel.from_zone, sel.to_zone, detail.pts)} style={{ height: 240 }} />}
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="filtrer (zone ou câble : FR, GB, NordLink…)"
        className="w-full rounded-lg border border-white/10 bg-surface-2/60 px-3 py-2 font-mono text-xs text-slate-200 placeholder:text-slate-600 focus:border-accent/40 focus:outline-none"
      />
      <p className="text-[10px] text-slate-500">
        {rows.length} frontière{rows.length > 1 ? "s" : ""} · triées par flux actuel ·
        flux mesuré (NTC/utilisation = M6)
      </p>
      <ul className="space-y-1">
        {rows.map(({ b, flow, cap }) => {
          const key = `${b.from_zone}|${b.to_zone}`;
          const dir =
            flow == null
              ? null
              : flow >= 0
                ? `${b.from_zone}→${b.to_zone}`
                : `${b.to_zone}→${b.from_zone}`;
          return (
            <li key={key}>
              <button
                onClick={() => setSel(b)}
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/10 bg-surface-2/40 px-3 py-2 text-left transition-colors hover:border-accent/30 hover:bg-surface-2/70"
              >
                <span className="min-w-0">
                  <span className="block font-mono text-xs text-slate-200">
                    {b.from_zone} – {b.to_zone}
                  </span>
                  <span className="block text-[10px] text-slate-500">
                    {b.capacity_regime === "FLOW_BASED" ? "flow-based" : "NTC"}
                    {b.gb_decoupled && " · GB"}
                    {cap > 0 && ` · ${gw(cap)}`}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  {flow == null ? (
                    <span className="font-mono text-[11px] text-slate-600">—</span>
                  ) : (
                    <>
                      <span className="block font-mono text-xs tabular-nums text-accent">
                        {mw(Math.abs(flow))}
                      </span>
                      <span className="block text-[10px] text-slate-500">{dir}</span>
                    </>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
