import { describe, expect, it } from "vitest";

import {
  kstLocalInputToIso,
  kstTodayLocalInput,
  toChartCandles,
} from "./chartData";

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

  it("maps aware API timestamps and decimal strings to chart values", () => {
    expect(
      toChartCandles([
        {
          timestamp: "2026-06-17T09:30:00+09:00",
          open: "100",
          high: "110",
          low: "90",
          close: "105",
          volume: 1000,
        },
      ]),
    ).toEqual([
      {
        time: 1_781_656_200,
        open: 100,
        high: 110,
        low: 90,
        close: 105,
      },
    ]);
  });
});
