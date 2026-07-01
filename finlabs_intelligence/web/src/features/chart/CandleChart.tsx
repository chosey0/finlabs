import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import { formatKrwCompact } from "./chartData";
import { ReactionHighlight, type ReactionBand } from "./reactionHighlight";
import type { ChartSelection } from "./chartSelection";
import { selectCandle } from "./chartSelection";

export type IndicatorKind = "volume" | "turnover";

export interface IndicatorSeries {
  readonly kind: IndicatorKind;
  readonly data: readonly HistogramData<UTCTimestamp>[];
}

interface CandleChartProps {
  readonly candles: readonly CandlestickData<UTCTimestamp>[];
  readonly indicator: IndicatorSeries | null;
  readonly reaction: ReactionBand | null;
  readonly onSelect: (selection: ChartSelection) => void;
  readonly selectedAt: number | null;
}

function timeFormatter(time: Time): string {
  return typeof time === "number"
    ? new Intl.DateTimeFormat("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(time * 1_000))
    : String(time);
}

export function CandleChart({
  candles,
  indicator,
  reaction,
  onSelect,
  selectedAt,
}: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 차트를 명령형으로 다루는 lightweight-charts는 React 밖에서 DOM을 소유한다.
  // 이 이펙트는 의존성이 바뀔 때마다 차트를 통째로 재생성/파기하므로, onSelect는
  // 호출부에서 useCallback으로 안정화해 불필요한 재빌드를 막아야 한다.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      height: 460,
      layout: {
        background: { type: ColorType.Solid, color: "#0c1220" },
        textColor: "#b7c2d7",
      },
      grid: {
        vertLines: { color: "#1b2638" },
        horzLines: { color: "#1b2638" },
      },
      localization: { timeFormatter },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    // 한국 시장 관례에 맞춰 상승은 빨강, 하락은 파랑으로 칠한다(서구와 반대).
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#ef5350",
      downColor: "#3b82f6",
      borderVisible: false,
      wickUpColor: "#ef5350",
      wickDownColor: "#3b82f6",
    });
    series.setData([...candles]);

    // Reaction window shading rides on the candle series so it tracks pan/zoom.
    const highlight = new ReactionHighlight();
    series.attachPrimitive(highlight);
    highlight.setBand(reaction);

    if (selectedAt !== null) {
      createSeriesMarkers(series, [
        {
          time: selectedAt as UTCTimestamp,
          position: "aboveBar",
          color: "#6ee7b7",
          shape: "arrowDown",
          text: "t0",
        },
      ]);
    }

    // Optional lower pane: 거래량 or 거래대금, colored to match the candles.
    if (indicator) {
      const histogram = chart.addSeries(
        HistogramSeries,
        indicator.kind === "turnover"
          ? { priceFormat: { type: "custom", minMove: 1, formatter: formatKrwCompact } }
          : { priceFormat: { type: "volume" } },
        1,
      );
      histogram.setData([...indicator.data]);
      // 가격 페인과 보조지표 페인을 3:1 높이로 나눠 캔들이 주가 되게 한다.
      const panes = chart.panes();
      if (panes.length > 1 && typeof panes[0].setStretchFactor === "function") {
        panes[0].setStretchFactor(3);
        panes[1].setStretchFactor(1);
      }
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

    // 재빌드/언마운트마다 옵저버·구독·차트를 모두 정리한다. chart.remove()를
    // 빠뜨리면 canvas와 리스너가 누수돼 종목을 바꿀 때마다 쌓인다.
    return () => {
      resize.disconnect();
      chart.unsubscribeClick(onClick);
      chart.remove();
    };
  }, [candles, indicator, reaction, onSelect, selectedAt]);

  return <div aria-label="1분봉 차트" className="chart" ref={containerRef} />;
}
