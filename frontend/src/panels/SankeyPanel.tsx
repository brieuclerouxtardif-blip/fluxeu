// Europe net-flow Sankey (M5, PLAN §4.5): who exports to whom, right now.
// Reads /api/metrics/sankey — a bipartite graph (export-side → import-side) so
// the layout is a clean left→right flow with no cycles. Node ids are prefixed
// ("x_FR" / "m_DE") for uniqueness; labels/tooltips strip the 2-char prefix.

import { useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import Chart from "../components/Chart";
import { fetchSankey } from "../api/client";
import type { SankeySnapshot } from "../types";

const REFRESH_MS = 5 * 60 * 1000;
const WARMING_MS = 15 * 1000;

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const TEAL = "#2dd4bf"; // export side
const AMBER = "#fbbf24"; // import side
const name2 = (id: string) => id.slice(2); // strip "x_" / "m_"
const mw = (v: number) => `${Math.round(v).toLocaleString("fr-FR")} MW`;

function sankeyOption(sk: SankeySnapshot): EChartsOption {
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(17,21,31,0.95)",
      borderColor: "rgba(148,163,184,0.25)",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as {
          dataType: "node" | "edge";
          name: string;
          value: number;
          data: { source?: string; target?: string };
        };
        if (d.dataType === "edge") {
          return `${name2(d.data.source!)} ▶ ${name2(d.data.target!)}<br/><b>${mw(d.value)}</b>`;
        }
        const side = d.name.startsWith("x_") ? "exporte" : "importe";
        return `<b>${name2(d.name)}</b> ${side}<br/>${mw(d.value)} au total`;
      },
    },
    series: [
      {
        type: "sankey",
        left: 8,
        right: 56,
        top: 8,
        bottom: 8,
        nodeWidth: 10,
        nodeGap: 7,
        draggable: false,
        emphasis: { focus: "adjacency" },
        data: sk.nodes.map((n) => ({
          name: n.id,
          itemStyle: { color: n.side === "export" ? TEAL : AMBER, borderColor: "transparent" },
        })),
        links: sk.links.map((l) => ({ source: l.source, target: l.target, value: l.value })),
        label: {
          color: "#cbd5e1",
          fontSize: 10,
          fontFamily: "monospace",
          formatter: (p: unknown) => name2((p as { name: string }).name),
        },
        lineStyle: { color: "gradient", opacity: 0.32, curveness: 0.5 },
      },
    ],
  };
}

export default function SankeyPanel() {
  const [sk, setSk] = useState<SankeySnapshot | null>(null);
  const [warming, setWarming] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await fetchSankey();
        if (cancelled) return;
        setSk(s);
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

  const option = useMemo(() => (sk ? sankeyOption(sk) : null), [sk]);

  if (!sk) {
    return (
      <p className="font-mono text-xs text-amber-300">
        {warming ? "◌ flux en préparation…" : "chargement…"}
      </p>
    );
  }

  const top = [...sk.links].sort((a, b) => b.value - a.value)[0];
  const exporters = new Set(sk.nodes.filter((n) => n.side === "export").map((n) => n.country));
  const dataTs = sk.data_ts ? tsFmt.format(new Date(sk.data_ts)) : "—";

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Échange total</div>
          <div className="font-mono text-base font-semibold text-slate-100">
            {(sk.total_mw / 1000).toFixed(1)} GW
          </div>
          <div className="text-[10px] text-slate-500">{sk.links.length} flux · {exporters.size} pays exp.</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Plus gros flux</div>
          <div className="font-mono text-base font-semibold text-slate-100">
            {top ? `${name2(top.source)}→${name2(top.target)}` : "—"}
          </div>
          <div className="text-[10px] text-slate-500">{top ? mw(top.value) : ""} · {dataTs}</div>
        </div>
      </div>

      <div className="flex items-center gap-3 text-[10px] text-slate-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: TEAL }} /> exporteur
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: AMBER }} /> importateur
        </span>
        <span className="text-slate-500">échanges commerciaux nets</span>
      </div>

      {option && <Chart option={option} style={{ height: 540 }} />}
    </div>
  );
}
