import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { ChartSelection } from "./chartSelection";
import { selectCandle } from "./chartSelection";

interface CandleChartProps {
  readonly candles: readonly CandlestickData<UTCTimestamp>[];
  readonly onSelect: (selection: ChartSelection) => void;
  readonly selectedAt: number | null;
}

export function CandleChart({ candles, onSelect, selectedAt }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      height: 440,
      layout: {
        background: { type: ColorType.Solid, color: "#0c1220" },
        textColor: "#b7c2d7",
      },
      grid: {
        vertLines: { color: "#1b2638" },
        horzLines: { color: "#1b2638" },
      },
      localization: {
        timeFormatter: (time: Time) =>
          typeof time === "number"
            ? new Intl.DateTimeFormat("ko-KR", {
                timeZone: "Asia/Seoul",
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
              }).format(new Date(time * 1_000))
            : String(time),
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#ef5350",
      downColor: "#3b82f6",
      borderVisible: false,
      wickUpColor: "#ef5350",
      wickDownColor: "#3b82f6",
    });
    series.setData([...candles]);
    if (selectedAt !== null) {
      createSeriesMarkers(series, [
        {
          time: selectedAt as UTCTimestamp,
          position: "aboveBar",
          color: "#6ee7b7",
          shape: "arrowDown",
          text: "선택",
        },
      ]);
    }
    chart.timeScale().fitContent();

    const onClick = (event: MouseEventParams) => {
      if (typeof event.time === "number") onSelect(selectCandle(event.time));
    };
    chart.subscribeClick(onClick);

    const resize = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
    });
    resize.observe(container);

    return () => {
      resize.disconnect();
      chart.unsubscribeClick(onClick);
      chart.remove();
    };
  }, [candles, onSelect, selectedAt]);

  return <div aria-label="1분봉 차트" className="chart" ref={containerRef} />;
}
