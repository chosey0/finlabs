import { useMemo } from "react";
import type { Data, Layout } from "plotly.js";

import type { CandleResponse } from "../../api/generated/types.gen";
import { DistributionPlot } from "./DistributionPlot";
import {
  filterCandlesByRange,
  metricValues,
  SHAPE_METRICS,
  type MetricSpec,
  type ShapeMetric,
  type TimeRange,
} from "./shapeMetrics";
import { securityColor, type DistributionWorkspace } from "./useDistribution";

interface DistributionPanelProps {
  readonly distribution: DistributionWorkspace;
}

interface LoadedEntry {
  readonly displayName: string;
  readonly color: string;
  readonly candles: readonly CandleResponse[];
}

// One histogram trace per security for a single metric, sharing fixed bins so
// the overlaid shapes are directly comparable across securities.
function metricTraces(
  entries: readonly LoadedEntry[],
  spec: MetricSpec,
  range: TimeRange | null,
  showLegend: boolean,
): Data[] {
  return entries.map((entry) => ({
    type: "histogram",
    x: metricValues(filterCandlesByRange(entry.candles, range), spec.key),
    name: entry.displayName,
    showlegend: showLegend,
    marker: { color: entry.color, line: { color: entry.color, width: 1 } },
    opacity: showLegend ? 0.55 : 0.8,
    histnorm: "probability",
    xbins: {
      start: spec.domain[0],
      end: spec.domain[1] + spec.binSize,
      size: spec.binSize,
    },
  }));
}

function metricLayout(spec: MetricSpec, showLegend: boolean): Partial<Layout> {
  return {
    title: { text: spec.label, font: { size: 12, color: "#e8edf6" } },
    showlegend: showLegend,
    legend: { orientation: "h", y: -0.18, font: { size: 10 } },
    xaxis: { range: [spec.domain[0], spec.domain[1]] },
    yaxis: { title: { text: "probability", font: { size: 10 } } },
  };
}

export function DistributionPanel({ distribution }: DistributionPanelProps) {
  const { basket, candlesBySecurity, range, metric, setMetric } = distribution;

  // Only securities whose candles actually loaded contribute a distribution.
  // Colors are keyed by basket position so a security's hue matches its chip.
  const entries = useMemo<LoadedEntry[]>(
    () =>
      basket
        .map((security, index) => ({ security, index }))
        .filter(({ security }) => security.security_id in candlesBySecurity)
        .map(({ security, index }) => ({
          displayName: security.display_name,
          color: securityColor(index),
          candles: candlesBySecurity[security.security_id] ?? [],
        })),
    [basket, candlesBySecurity],
  );

  const isMulti = entries.length > 1;
  const activeSpec = SHAPE_METRICS.find((spec) => spec.key === metric) ?? SHAPE_METRICS[0];

  // Single security: all four shape metrics side by side. N securities: the one
  // selected metric, overlaid per security.
  const single = useMemo(
    () =>
      entries.length === 1
        ? SHAPE_METRICS.map((spec) => ({
            spec,
            data: metricTraces(entries, spec, range, false),
            layout: metricLayout(spec, false),
          }))
        : [],
    [entries, range],
  );
  const multiData = useMemo(
    () => (isMulti ? metricTraces(entries, activeSpec, range, true) : []),
    [entries, activeSpec, range, isMulti],
  );
  const multiLayout = useMemo(() => metricLayout(activeSpec, true), [activeSpec]);

  const selectionLabel = range ? "선택한 구간" : "전체 구간";

  return (
    <section aria-label="분포" className="pane dist-pane">
      <header className="pane-head">
        <h2>분포 <span className="chart-title-meta">· {selectionLabel}</span></h2>
        {isMulti ? (
          <label className="chart-indicator">메트릭
            <select
              aria-label="분포 메트릭"
              onChange={(event) => setMetric(event.target.value as ShapeMetric)}
              value={metric}
            >
              {SHAPE_METRICS.map((spec) => (
                <option key={spec.key} value={spec.key}>{spec.label}</option>
              ))}
            </select>
          </label>
        ) : null}
      </header>
      <div className="pane-body">
        {entries.length === 0 ? (
          <div className="chart-empty">
            종목을 추가하고 차트를 불러오면 캔들 형태 분포를 표시합니다.
          </div>
        ) : entries.length === 1 ? (
          <div className="dist-grid">
            {single.map(({ spec, data, layout }) => (
              <DistributionPlot key={spec.key} data={data} height={240} layout={layout} />
            ))}
          </div>
        ) : (
          <DistributionPlot data={multiData} height={460} layout={multiLayout} />
        )}
      </div>
    </section>
  );
}
