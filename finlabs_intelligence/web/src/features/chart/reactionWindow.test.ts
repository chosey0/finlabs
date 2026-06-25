import { describe, expect, it } from "vitest";

import { reactionWindowEnd } from "./reactionWindow";

function kst(iso: string): number {
  return Math.floor(Date.parse(`${iso}+09:00`) / 1_000);
}

describe("reactionWindowEnd", () => {
  it("stays in the same session when 30 trading minutes fit before the close", () => {
    // Wed 09:31 + 30 min → 10:01 the same day.
    expect(reactionWindowEnd(kst("2026-06-17T09:31:00"))).toBe(
      kst("2026-06-17T10:01:00"),
    );
  });

  it("rolls past the close into the next trading session", () => {
    // Wed 15:20 has 10 min to the close; the remaining 20 land at 09:20 Thu.
    expect(reactionWindowEnd(kst("2026-06-17T15:20:00"))).toBe(
      kst("2026-06-18T09:20:00"),
    );
  });

  it("skips the weekend when rolling forward from a Friday close", () => {
    // Fri 15:20 → 20 trading minutes carry over to Monday 09:20.
    expect(reactionWindowEnd(kst("2026-06-19T15:20:00"))).toBe(
      kst("2026-06-22T09:20:00"),
    );
  });

  it("counts from the open when t0 sits before the session starts", () => {
    expect(reactionWindowEnd(kst("2026-06-17T08:00:00"))).toBe(
      kst("2026-06-17T09:30:00"),
    );
  });
});
