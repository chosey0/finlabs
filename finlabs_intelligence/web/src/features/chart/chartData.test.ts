import { describe, expect, it } from "vitest";

import {
  formatKrwCompact,
  kstLocalInputToIso,
  kstLocalInputToUnix,
  kstTodayLocalInput,
  kstUnixToLocalInput,
  toChartCandles,
  toTurnoverHistogram,
  toVolumeHistogram,
} from "./chartData";

const SAMPLE = {
  timestamp: "2026-06-17T09:30:00+09:00",
  open: "100",
  high: "110",
  low: "90",
  close: "105",
  volume: 1000,
  turnover: "105000",
} as const;

describe("chart data boundary", () => {
  it("keeps an explicit KST offset for API range queries", () => {
    expect(kstLocalInputToIso("2026-06-17T09:30")).toBe(
      "2026-06-17T09:30:00+09:00",
    );
  });

  it("builds initial chart inputs from today's KST date", () => {
    const beforeKstMidnight = new Date("2026-06-22T14:59:59Z");
    const afterKstMidnight = new Date("2026-06-22T15:00:00Z");

    expect(kstTodayLocalInput("09:00", beforeKstMidnight)).toBe(
      "2026-06-22T09:00",
    );
    expect(kstTodayLocalInput("15:30", afterKstMidnight)).toBe(
      "2026-06-23T15:30",
    );
  });

  it("round-trips a KST instant through the datetime-local input format", () => {
    expect(kstUnixToLocalInput(1_781_656_200)).toBe("2026-06-17T09:30");
    expect(kstLocalInputToUnix("2026-06-17T09:30")).toBe(1_781_656_200);
  });

  it("maps aware API timestamps and decimal strings to chart values", () => {
    expect(toChartCandles([SAMPLE])).toEqual([
      {
        time: 1_781_656_200,
        open: 100,
        high: 110,
        low: 90,
        close: 105,
      },
    ]);
  });

  it("colors histogram bars red when the candle closed up, blue when down", () => {
    const up = { ...SAMPLE, open: "100", close: "105" };
    const down = { ...SAMPLE, open: "105", close: "100" };
    expect(toVolumeHistogram([up])[0]).toMatchObject({
      time: 1_781_656_200,
      value: 1000,
      color: "rgba(239, 83, 80, 0.55)",
    });
    expect(toTurnoverHistogram([down])[0]).toMatchObject({
      value: 105000,
      color: "rgba(59, 130, 246, 0.55)",
    });
  });

  it("labels turnover in Korean compact units", () => {
    expect(formatKrwCompact(1_200_000_000_000)).toBe("1.2조");
    expect(formatKrwCompact(34_000_000_000)).toBe("340억");
    expect(formatKrwCompact(56_000)).toBe("6만");
    expect(formatKrwCompact(420)).toBe("420");
  });
});
