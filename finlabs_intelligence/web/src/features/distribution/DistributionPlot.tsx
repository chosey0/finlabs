import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { Data, Layout } from "plotly.js";

interface DistributionPlotProps {
  readonly data: readonly Data[];
  readonly layout: Partial<Layout>;
  readonly height: number;
}

// Shared dark theme so every histogram reads against the same panel background
// as the rest of the workbench; per-plot layout (title, x-range, legend) is
// merged on top by the caller.
const BASE_LAYOUT: Partial<Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#b7c2d7", size: 11 },
  margin: { l: 44, r: 16, t: 34, b: 32 },
  bargap: 0.04,
  barmode: "overlay",
  xaxis: { gridcolor: "#1b2638", zerolinecolor: "#33445f" },
  yaxis: { gridcolor: "#1b2638", zerolinecolor: "#33445f" },
};

// Thin imperative wrapper around plotly.js — mirrors how CandleChart wraps
// lightweight-charts — so we avoid the react-plotly.js peer-dependency dance on
// React 19. Plotly.react diffs against the previous render, and purge frees the
// graph div on unmount.
export function DistributionPlot({ data, layout, height }: DistributionPlotProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const merged: Partial<Layout> = {
      ...BASE_LAYOUT,
      ...layout,
      height,
      xaxis: { ...BASE_LAYOUT.xaxis, ...layout.xaxis },
      yaxis: { ...BASE_LAYOUT.yaxis, ...layout.yaxis },
    };
    void Plotly.react(el, data as Data[], merged, {
      displayModeBar: false,
      responsive: true,
    });
    const resize = new ResizeObserver(() => {
      void Plotly.Plots.resize(el);
    });
    resize.observe(el);
    return () => {
      resize.disconnect();
      Plotly.purge(el);
    };
  }, [data, layout, height]);

  return <div className="dist-plot" ref={ref} />;
}
