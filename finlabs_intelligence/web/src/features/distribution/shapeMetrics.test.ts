import { describe, expect, it } from "vitest";

import type { CandleResponse } from "../../api/generated/types.gen";
import {
  candleUnix,
  extractShapeFeature,
  filterCandlesByRange,
  metricValues,
} from "./shapeMetrics";

function candle(part: Partial<CandleResponse>): CandleResponse {
  return {
    timestamp: "2026-06-17T09:00:00+09:00",
    open: "100",
    high: "100",
    low: "100",
    close: "100",
    volume: 0,
    turnover: "0",
    ...part,
  };
}

describe("extractShapeFeature", () => {
  it("returns all-zero for a flat candle (no range)", () => {
    expect(extractShapeFeature(candle({ open: "50", high: "50", low: "50", close: "50" }))).toEqual({
      signed_body_ratio: 0,
      upper_ratio: 0,
      lower_ratio: 0,
      body_center_location: 0,
    });
  });

  it("signs the body ratio by direction and centers a symmetric candle at zero", () => {
    // open 10, close 14, low 8, high 16 → range 8, body 4 (up).
    // upper wick 16-14=2, lower wick 10-8=2 → symmetric, center at midpoint.
    const up = extractShapeFeature(candle({ open: "10", high: "16", low: "8", close: "14" }));
    expect(up.signed_body_ratio).toBeCloseTo(0.5, 10);
    expect(up.upper_ratio).toBeCloseTo(0.25, 10);
    expect(up.lower_ratio).toBeCloseTo(0.25, 10);
    expect(up.body_center_location).toBeCloseTo(0, 10);

    // Same geometry, falling: only the body sign flips.
    const down = extractShapeFeature(candle({ open: "14", high: "16", low: "8", close: "10" }));
    expect(down.signed_body_ratio).toBeCloseTo(-0.5, 10);
    expect(down.upper_ratio).toBeCloseTo(0.25, 10);
    expect(down.lower_ratio).toBeCloseTo(0.25, 10);
  });

  it("maps body_center_location to [-1, 1] by where the body sits in the range", () => {
    // Body hugging the top of the range → location near +1.
    const top = extractShapeFeature(candle({ open: "18", high: "20", low: "0", close: "20" }));
    expect(top.body_center_location).toBeCloseTo(0.9, 10);
    // Body hugging the bottom → location near -1.
    const bottom = extractShapeFeature(candle({ open: "0", high: "20", low: "0", close: "2" }));
    expect(bottom.body_center_location).toBeCloseTo(-0.9, 10);
  });
});

describe("filterCandlesByRange", () => {
  const series = [
    candle({ timestamp: "2026-06-17T09:00:00+09:00" }),
    candle({ timestamp: "2026-06-17T09:01:00+09:00" }),
    candle({ timestamp: "2026-06-17T09:02:00+09:00" }),
  ];

  it("returns every candle when the range is null", () => {
    expect(filterCandlesByRange(series, null)).toHaveLength(3);
  });

  it("keeps candles inside an inclusive window regardless of bound order", () => {
    const start = candleUnix(series[0]);
    const end = candleUnix(series[1]);
    expect(filterCandlesByRange(series, { start, end })).toHaveLength(2);
    // Reversed bounds (drag right-to-left) select the same window.
    expect(filterCandlesByRange(series, { start: end, end: start })).toHaveLength(2);
  });
});

describe("metricValues", () => {
  it("projects a single metric across candles", () => {
    const values = metricValues(
      [
        candle({ open: "10", high: "16", low: "8", close: "14" }),
        candle({ open: "14", high: "16", low: "8", close: "10" }),
      ],
      "signed_body_ratio",
    );
    expect(values).toHaveLength(2);
    expect(values[0]).toBeCloseTo(0.5, 10);
    expect(values[1]).toBeCloseTo(-0.5, 10);
  });
});
