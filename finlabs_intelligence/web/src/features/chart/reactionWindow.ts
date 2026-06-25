// Mirror of the backend session grid (modules/.../session_grid.py): the reaction
// label measures HORIZON_MINUTES *trading* minutes after t0, counted only inside
// the KST regular session (09:00–15:30) and rolling forward across the close into
// later weekday sessions. We approximate trading days as weekdays — the frontend
// has no holiday calendar, so this is a visual aid, not the authoritative label.

const OPEN_MINUTE = 9 * 60; // 09:00
const CLOSE_MINUTE = 15 * 60 + 30; // 15:30
const SESSION_MINUTES = CLOSE_MINUTE - OPEN_MINUTE; // 390
export const REACTION_HORIZON_MINUTES = 30;

interface KstDate {
  readonly year: number;
  readonly month: number; // 1-12
  readonly day: number;
  readonly minuteOfDay: number;
}

function kstDateParts(unixSeconds: number): KstDate {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(unixSeconds * 1_000));
  const v = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: Number(v.year),
    month: Number(v.month),
    day: Number(v.day),
    minuteOfDay: Number(v.hour) * 60 + Number(v.minute),
  };
}

// Advance a KST calendar date to the next weekday (skipping Sat/Sun). UTC math on
// a date-only value keeps the weekday correct without timezone drift.
function nextTradingDay(year: number, month: number, day: number) {
  const cursor = new Date(Date.UTC(year, month - 1, day));
  do {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  } while (cursor.getUTCDay() === 0 || cursor.getUTCDay() === 6);
  return {
    year: cursor.getUTCFullYear(),
    month: cursor.getUTCMonth() + 1,
    day: cursor.getUTCDate(),
  };
}

function kstWallClockToUnix(
  year: number,
  month: number,
  day: number,
  minuteOfDay: number,
): number {
  const yyyy = String(year).padStart(4, "0");
  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  const hh = String(Math.floor(minuteOfDay / 60)).padStart(2, "0");
  const mi = String(minuteOfDay % 60).padStart(2, "0");
  return Math.floor(Date.parse(`${yyyy}-${mm}-${dd}T${hh}:${mi}:00+09:00`) / 1_000);
}

export function reactionWindowEnd(
  t0Unix: number,
  tradingMinutes: number = REACTION_HORIZON_MINUTES,
): number {
  let { year, month, day } = kstDateParts(t0Unix);
  const { minuteOfDay } = kstDateParts(t0Unix);
  // Clamp t0 into the session; news anchored before the open starts counting at
  // 09:00, and anything at/after the close starts the next session.
  const startMinute = Math.min(Math.max(minuteOfDay, OPEN_MINUTE), CLOSE_MINUTE);
  let remaining = tradingMinutes;

  const availableToday = CLOSE_MINUTE - startMinute;
  if (remaining <= availableToday) {
    return kstWallClockToUnix(year, month, day, startMinute + remaining);
  }

  remaining -= availableToday;
  for (;;) {
    ({ year, month, day } = nextTradingDay(year, month, day));
    if (remaining <= SESSION_MINUTES) {
      return kstWallClockToUnix(year, month, day, OPEN_MINUTE + remaining);
    }
    remaining -= SESSION_MINUTES;
  }
}
