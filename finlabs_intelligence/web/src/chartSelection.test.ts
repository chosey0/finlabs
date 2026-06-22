import { describe, expect, it } from "vitest";

import { selectCandle } from "./chartSelection";

describe("selectCandle", () => {
  it("keeps the exact clicked timestamp and creates the inclusive prior-hour window", () => {
    expect(selectCandle(1_767_056_320)).toEqual({
      selectedAt: 1_767_056_320,
      windowStart: 1_767_052_720,
      windowEnd: 1_767_056_320,
    });
  });

  it.each([0, -1, 1.5, Number.NaN])("rejects invalid timestamps", (value) => {
    expect(() => selectCandle(value)).toThrow();
  });
});
