import { describe, expect, it } from "vitest";

import { selectCandle, selectWindow } from "./chartSelection";
import { describeNewsWindow } from "./newsWindow";

function unix(kstMinute: string): number {
  return Math.floor(Date.parse(`2026-06-26T${kstMinute}:00+09:00`) / 1_000);
}

describe("describeNewsWindow", () => {
  it("describes a clicked candle as a time-based prior window", () => {
    const facts = describeNewsWindow(selectCandle(unix("10:10")));

    expect(facts.t0Label).toBe("2026-06-26 10:10");
    expect(facts.directionLabel).toBe("t0 이전");
    expect(facts.basisLabel).toBe("직전 60분"); // logic is t0 - 3600s
    expect(facts.rangeStartLabel).toBe("2026-06-26 09:10");
    expect(facts.rangeEndLabel).toBe("2026-06-26 10:10");
    expect(facts.timezoneLabel).toBe("KST");
    expect(facts.source).toBe("candle");
    expect(facts.sourceLabel).toBe("캔들 자동 선택");
    expect(facts.spanMinutes).toBe(60);
  });

  it("marks a typed window as 직접 입력 구간 with its own span", () => {
    const facts = describeNewsWindow(selectWindow(unix("09:40"), unix("10:10")));

    expect(facts.basisLabel).toBe("직전 30분");
    expect(facts.spanMinutes).toBe(30);
    expect(facts.source).toBe("manual");
    expect(facts.sourceLabel).toBe("직접 입력 구간");
    expect(facts.rangeStartLabel).toBe("2026-06-26 09:40");
  });
});
