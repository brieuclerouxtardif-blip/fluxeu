// Thin self-managed ECharts wrapper — no react binding lib (robust on React 19).
// Inits once, pushes new options on change (notMerge), resizes with the box,
// disposes on unmount. Background stays transparent so it sits on dark surfaces.

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  option: echarts.EChartsOption;
  className?: string;
  style?: React.CSSProperties;
}

export default function Chart({ option, className, style }: Props) {
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!elRef.current) return;
    const chart = echarts.init(elRef.current, null, { renderer: "canvas" });
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(elRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={elRef} className={className} style={style} />;
}
