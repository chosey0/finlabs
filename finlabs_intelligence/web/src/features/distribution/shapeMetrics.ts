import type { CandleResponse } from "../../api/generated/types.gen";

// Price-shape features, ported 1:1 from the research notebook
// (research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py
// :extract_price_shape_feature). These describe a single candle's geometry
// independent of price scale, so the workbench can chart their distribution.
export type ShapeMetric =
  | "signed_body_ratio"
  | "upper_ratio"
  | "lower_ratio"
  | "body_center_location";

export interface ShapeFeature {
  readonly signed_body_ratio: number;
  readonly upper_ratio: number;
  readonly lower_ratio: number;
  readonly body_center_location: number;
}

// Display metadata for every metric, kept in one place so the metric picker,
// the single-security grid, and the histogram bins all read from the same
// source of truth. `domain` is the metric's natural value range and seeds the
// fixed Plotly bins so traces from different securities line up.
export interface MetricSpec {
  readonly key: ShapeMetric;
  readonly label: string;
  readonly domain: readonly [number, number];
  readonly binSize: number;
}

export const SHAPE_METRICS: readonly MetricSpec[] = [
  { key: "signed_body_ratio", label: "Signed Body Ratio", domain: [-1, 1], binSize: 0.1 },
  { key: "upper_ratio", label: "Upper Ratio", domain: [0, 1], binSize: 0.05 },
  { key: "lower_ratio", label: "Lower Ratio", domain: [0, 1], binSize: 0.05 },
  { key: "body_center_location", label: "Body Center Location", domain: [-1, 1], binSize: 0.1 },
];

function direction(open: number, close: number): number {
  if (close > open) return 1;
  if (close < open) return -1;
  return 0;
}

// A flat candle (high === low) has no shape; the notebook returns all-zero in
// that case to avoid dividing by a zero range, and we mirror that exactly.
export function extractShapeFeature(candle: CandleResponse): ShapeFeature {
  const open = Number(candle.open);
  const high = Number(candle.high);
  const low = Number(candle.low);
  const close = Number(candle.close);

  const totalRange = Math.max(high - low, 0);
  if (totalRange === 0) {
    return {
      signed_body_ratio: 0,
      upper_ratio: 0,
      lower_ratio: 0,
      body_center_location: 0,
    };
  }

  const bodyTop = Math.max(open, close);
  const bodyBottom = Math.min(open, close);
  const bodyRatio = Math.abs(close - open) / totalRange;

  const bodyCenter = (open + close) / 2;
  const bodyCenterPosition = (bodyCenter - low) / totalRange;

  return {
    signed_body_ratio: bodyRatio * direction(open, close),
    upper_ratio: Math.max(high - bodyTop, 0) / totalRange,
    lower_ratio: Math.max(bodyBottom - low, 0) / totalRange,
    body_center_location: 2 * bodyCenterPosition - 1,
  };
}

// Unix seconds for a candle, matching how lightweight-charts keys its data so a
// chart-selected time window can filter the same candle array.
export function candleUnix(candle: CandleResponse): number {
  const milliseconds = Date.parse(candle.timestamp);
  if (!Number.isFinite(milliseconds)) {
    throw new Error(`invalid candle timestamp: ${candle.timestamp}`);
  }
  return Math.floor(milliseconds / 1_000);
}

export interface TimeRange {
  readonly start: number;
  readonly end: number;
}

// Keep candles whose time falls inside [start, end] (inclusive). A null range
// means "no drag selection" and yields every candle — the spec's default of
// treating all loaded candles as the distribution region.
export function filterCandlesByRange(
  candles: readonly CandleResponse[],
  range: TimeRange | null,
): readonly CandleResponse[] {
  if (!range) return candles;
  const lo = Math.min(range.start, range.end);
  const hi = Math.max(range.start, range.end);
  return candles.filter((candle) => {
    const time = candleUnix(candle);
    return time >= lo && time <= hi;
  });
}

// The metric column for a set of candles: extract every feature then project the
// one metric. This is the array a histogram trace consumes.
export function metricValues(
  candles: readonly CandleResponse[],
  metric: ShapeMetric,
): number[] {
  return candles.map((candle) => extractShapeFeature(candle)[metric]);
}
