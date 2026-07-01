import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type CandlestickData,
  type IChartApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import { ReactionHighlight } from "../chart/reactionHighlight";
import type { TimeRange } from "./shapeMetrics";

interface DistributionCandleChartProps {
  readonly candles: readonly CandlestickData<UTCTimestamp>[];
  readonly range: TimeRange | null;
  readonly onSelectRange: (range: TimeRange | null) => void;
}

// A horizontal drag shorter than this many pixels is read as a click — used to
// clear the current selection rather than create a one-candle window.
const DRAG_THRESHOLD_PX = 4;

interface DragState {
  active: boolean;
  startTime: number | null;
}

function bandFromRange(range: TimeRange | null) {
  if (!range) return null;
  return {
    from: Math.min(range.start, range.end) as UTCTimestamp,
    to: Math.max(range.start, range.end) as UTCTimestamp,
  };
}

// Candlestick chart whose distinguishing feature is drag-to-select: the analyst
// drags horizontally to pick the time window the distribution panel measures.
// Built on lightweight-charts (the rest of the app's charts) with chart panning
// disabled so the press-drag gesture is free for range selection; the shaded
// band reuses the ReactionHighlight series primitive.
export function DistributionCandleChart({
  candles,
  range,
  onSelectRange,
}: DistributionCandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const highlightRef = useRef<ReactionHighlight | null>(null);
  // Latest values read from inside long-lived DOM listeners without forcing the
  // chart-creation effect to re-run (which would tear down the chart).
  const rangeRef = useRef(range);
  const onSelectRef = useRef(onSelectRange);
  rangeRef.current = range;
  onSelectRef.current = onSelectRange;

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
      timeScale: { timeVisible: true, secondsVisible: false },
      // Free the press-drag gesture for selection; zoom stays on the wheel.
      handleScroll: {
        pressedMouseMove: false,
        horzTouchDrag: false,
        vertTouchDrag: false,
        mouseWheel: true,
      },
      handleScale: {
        axisPressedMouseMove: false,
        axisDoubleClickReset: { time: true, price: true },
        mouseWheel: true,
        pinch: true,
      },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#ef5350",
      downColor: "#3b82f6",
      borderVisible: false,
      wickUpColor: "#ef5350",
      wickDownColor: "#3b82f6",
    });
    series.setData([...candles]);

    const highlight = new ReactionHighlight();
    series.attachPrimitive(highlight);
    highlight.setBand(bandFromRange(rangeRef.current));
    highlightRef.current = highlight;

    chart.timeScale().fitContent();

    const drag: DragState = { active: false, startTime: null };
    const timeScale = chart.timeScale();

    // Snap a pixel x within the chart to the nearest candle time. Outside the
    // data, coordinateToTime returns null, so we clamp to the first/last candle.
    const timeAt = (clientX: number): number | null => {
      const rect = container.getBoundingClientRect();
      const x = clientX - rect.left;
      const snapped = timeScale.coordinateToTime(x) as number | null;
      if (snapped !== null) return snapped;
      if (candles.length === 0) return null;
      const first = candles[0].time as number;
      const last = candles[candles.length - 1].time as number;
      return x < rect.width / 2 ? first : last;
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      drag.active = true;
      drag.startTime = timeAt(event.clientX);
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!drag.active || drag.startTime === null) return;
      const current = timeAt(event.clientX);
      if (current === null) return;
      highlight.setBand({
        from: Math.min(drag.startTime, current) as UTCTimestamp,
        to: Math.max(drag.startTime, current) as UTCTimestamp,
      });
    };

    const onPointerUp = (event: PointerEvent) => {
      if (!drag.active) return;
      drag.active = false;
      const rect = container.getBoundingClientRect();
      const startX = drag.startTime === null ? null : timeScale.timeToCoordinate(drag.startTime as Time);
      const movedFar =
        startX !== null && Math.abs(event.clientX - rect.left - startX) > DRAG_THRESHOLD_PX;
      const end = timeAt(event.clientX);
      if (!movedFar || drag.startTime === null || end === null) {
        // A click (no real drag) clears the selection back to "all candles".
        highlight.setBand(null);
        onSelectRef.current(null);
        return;
      }
      const next: TimeRange = {
        start: Math.min(drag.startTime, end),
        end: Math.max(drag.startTime, end),
      };
      highlight.setBand(bandFromRange(next));
      onSelectRef.current(next);
    };

    container.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);

    const resize = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
    });
    resize.observe(container);

    return () => {
      resize.disconnect();
      container.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      chart.remove();
      chartRef.current = null;
      highlightRef.current = null;
    };
  }, [candles]);

  // Keep the shaded band in sync when the range is changed from outside the
  // chart (e.g. the "전체 구간" reset button) without rebuilding the chart.
  useEffect(() => {
    highlightRef.current?.setBand(bandFromRange(range));
  }, [range]);

  return <div aria-label="분포 구간 차트" className="chart" ref={containerRef} />;
}
