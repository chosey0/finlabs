import { describe, expect, it } from "vitest";

import { selectCandle, selectWindow } from "./chartSelection";

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

describe("selectWindow", () => {
  it("anchors t0 on the typed window end and keeps both bounds", () => {
    expect(selectWindow(1_767_050_000, 1_767_056_320)).toEqual({
      selectedAt: 1_767_056_320,
      windowStart: 1_767_050_000,
      windowEnd: 1_767_056_320,
    });
  });

  it("rejects a window whose start is not before its end", () => {
    expect(() => selectWindow(1_767_056_320, 1_767_056_320)).toThrow();
    expect(() => selectWindow(1_767_056_321, 1_767_056_320)).toThrow();
  });

  it.each([0, -1, 1.5, Number.NaN])("rejects invalid bounds", (value) => {
    expect(() => selectWindow(value, 1_767_056_320)).toThrow();
  });
});
