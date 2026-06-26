import { formatKstMinute } from "./chartData";
import type { ChartSelection, SelectionSource } from "./chartSelection";

export interface NewsWindowFacts {
  readonly t0Label: string;
  /** Always "t0 이전" today: the window spans the time *before* t0. */
  readonly directionLabel: string;
  /**
   * Search basis. The window is time-based (t0 − span), so this reads in
   * minutes (e.g. "직전 60분") rather than a bar count, matching the logic.
   */
  readonly basisLabel: string;
  readonly rangeStartLabel: string;
  readonly rangeEndLabel: string;
  readonly timezoneLabel: string;
  readonly sourceLabel: string;
  readonly source: SelectionSource;
  readonly spanMinutes: number;
}

// Describe the news search window in unambiguous terms. The underlying window is
// [windowStart, t0) — a real *time* span before t0 — so the basis is expressed
// in minutes, and the concrete start/end instants are reported separately.
export function describeNewsWindow(
  selection: ChartSelection,
): NewsWindowFacts {
  const spanMinutes = Math.round(
    (selection.windowEnd - selection.windowStart) / 60,
  );
  return {
    t0Label: formatKstMinute(selection.selectedAt),
    directionLabel: "t0 이전",
    basisLabel: `직전 ${spanMinutes}분`,
    rangeStartLabel: formatKstMinute(selection.windowStart),
    rangeEndLabel: formatKstMinute(selection.windowEnd),
    timezoneLabel: "KST",
    sourceLabel: selection.source === "manual" ? "직접 입력 구간" : "캔들 자동 선택",
    source: selection.source,
    spanMinutes,
  };
}
