// The slice of a chart workspace the ChartSetupBridge reads: which candles to
// fetch (bar type, interval, date range). Pulled out so both the news workbench
// (useChart) and the distribution workbench (useDistribution) can drive the same
// bridge without sharing the rest of their very different state.
export interface ChartSetupControls {
  readonly startAt: string;
  readonly setStartAt: (value: string) => void;
  readonly endAt: string;
  readonly setEndAt: (value: string) => void;
  readonly chartType: "minute" | "daily";
  readonly setChartType: (value: "minute" | "daily") => void;
  readonly intervalMinutes: number;
  readonly setIntervalMinutes: (value: number) => void;
}
