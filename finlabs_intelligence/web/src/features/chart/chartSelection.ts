export type CandleTime = number;

export interface ChartSelection {
  readonly selectedAt: CandleTime;
  readonly windowStart: CandleTime;
  readonly windowEnd: CandleTime;
}

const ONE_HOUR_SECONDS = 60 * 60;

export function selectCandle(selectedAt: CandleTime): ChartSelection {
  if (!Number.isInteger(selectedAt) || selectedAt <= 0) {
    throw new Error("selectedAt must be a positive Unix timestamp");
  }
  return {
    selectedAt,
    windowStart: selectedAt - ONE_HOUR_SECONDS,
    windowEnd: selectedAt,
  };
}

// Direct-entry counterpart to selectCandle: the analyst pins both ends of the
// news search window. windowEnd stays t0 — the reaction anchor — so a typed
// window and a clicked candle produce the same shape downstream.
export function selectWindow(
  windowStart: CandleTime,
  windowEnd: CandleTime,
): ChartSelection {
  for (const value of [windowStart, windowEnd]) {
    if (!Number.isInteger(value) || value <= 0) {
      throw new Error("window bounds must be positive Unix timestamps");
    }
  }
  if (windowStart >= windowEnd) {
    throw new Error("windowStart must be before windowEnd");
  }
  return { selectedAt: windowEnd, windowStart, windowEnd };
}
