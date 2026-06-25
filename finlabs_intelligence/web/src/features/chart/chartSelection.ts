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
