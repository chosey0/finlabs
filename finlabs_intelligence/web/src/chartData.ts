import type { CandlestickData, UTCTimestamp } from "lightweight-charts";

import type { CandleResponse } from "./api/generated/types.gen";

export function toChartCandles(
  candles: readonly CandleResponse[],
): CandlestickData<UTCTimestamp>[] {
  return candles.map((candle) => {
    const milliseconds = Date.parse(candle.timestamp);
    if (!Number.isFinite(milliseconds)) {
      throw new Error(`invalid candle timestamp: ${candle.timestamp}`);
    }
    return {
      time: Math.floor(milliseconds / 1_000) as UTCTimestamp,
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close),
    };
  });
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

export function formatKstTimestamp(unixSeconds: number): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
  }).format(new Date(unixSeconds * 1_000));
}
