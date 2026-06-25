import type { CandlestickData, HistogramData, UTCTimestamp } from "lightweight-charts";

import type { CandleResponse } from "../../api/generated/types.gen";

// Korea convention (and Toss): rising candles are red, falling are blue. The
// histogram bars reuse these so volume/turnover read against the same color.
const UP_COLOR = "rgba(239, 83, 80, 0.55)";
const DOWN_COLOR = "rgba(59, 130, 246, 0.55)";

function candleTime(candle: CandleResponse): UTCTimestamp {
  const milliseconds = Date.parse(candle.timestamp);
  if (!Number.isFinite(milliseconds)) {
    throw new Error(`invalid candle timestamp: ${candle.timestamp}`);
  }
  return Math.floor(milliseconds / 1_000) as UTCTimestamp;
}

export function toChartCandles(
  candles: readonly CandleResponse[],
): CandlestickData<UTCTimestamp>[] {
  return candles.map((candle) => ({
    time: candleTime(candle),
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  }));
}

function toHistogram(
  candles: readonly CandleResponse[],
  value: (candle: CandleResponse) => number,
): HistogramData<UTCTimestamp>[] {
  return candles.map((candle) => ({
    time: candleTime(candle),
    value: value(candle),
    color: Number(candle.close) >= Number(candle.open) ? UP_COLOR : DOWN_COLOR,
  }));
}

export function toVolumeHistogram(
  candles: readonly CandleResponse[],
): HistogramData<UTCTimestamp>[] {
  return toHistogram(candles, (candle) => candle.volume);
}

export function toTurnoverHistogram(
  candles: readonly CandleResponse[],
): HistogramData<UTCTimestamp>[] {
  return toHistogram(candles, (candle) => Number(candle.turnover));
}

// Compact KRW for the turnover scale, e.g. 1.2조 / 340억 / 5.6만, the way Korean
// brokerages label 거래대금.
export function formatKrwCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
  if (abs >= 1e8) return `${Math.round(value / 1e8)}억`;
  if (abs >= 1e4) return `${Math.round(value / 1e4)}만`;
  return String(Math.round(value));
}

export function kstLocalInputToIso(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    throw new Error("날짜와 시간을 분 단위까지 입력하세요.");
  }
  return `${value}:00+09:00`;
}

export function kstTodayLocalInput(
  time: string,
  now: Date = new Date(),
): string {
  if (!/^\d{2}:\d{2}$/.test(time)) {
    throw new Error("시간을 분 단위까지 입력하세요.");
  }
  const dateParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(
    dateParts.map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}T${time}`;
}

// datetime-local <input> works in wall-clock time; these two helpers convert
// between a KST Unix instant and that minute-precision string so a clicked
// candle can seed the manual window inputs and vice versa.
export function kstUnixToLocalInput(unixSeconds: number): string {
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
  return `${v.year}-${v.month}-${v.day}T${v.hour}:${v.minute}`;
}

export function kstLocalInputToUnix(value: string): number {
  return Math.floor(Date.parse(kstLocalInputToIso(value)) / 1_000);
}

export function formatKstTimestamp(unixSeconds: number): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
  }).format(new Date(unixSeconds * 1_000));
}
