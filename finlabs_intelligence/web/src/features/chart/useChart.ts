import { useCallback, useMemo, useState } from "react";

import { loadChart as loadChartApi, type CatalogItemResponse, type ChartResponse } from "../../shared/api";
import { kstLocalInputToIso, kstTodayLocalInput, toChartCandles } from "./chartData";
import type { ChartSelection } from "./chartSelection";

interface Deps {
  readonly security: CatalogItemResponse | null;
  readonly setStatus: (message: string) => void;
  readonly setBusy: (busy: boolean) => void;
}

export interface ChartWorkspace {
  readonly startAt: string;
  readonly setStartAt: (value: string) => void;
  readonly endAt: string;
  readonly setEndAt: (value: string) => void;
  readonly chartType: "minute" | "daily";
  readonly setChartType: (value: "minute" | "daily") => void;
  readonly intervalMinutes: number;
  readonly setIntervalMinutes: (value: number) => void;
  readonly chart: ChartResponse | null;
  readonly selection: ChartSelection | null;
  readonly chartExpanded: boolean;
  readonly setChartExpanded: (updater: (current: boolean) => boolean) => void;
  readonly chartCandles: ReturnType<typeof toChartCandles>;
  readonly handleSelection: (next: ChartSelection) => void;
  readonly loadChart: () => Promise<void>;
  readonly reset: () => void;
}

export function useChart({ security, setStatus, setBusy }: Deps): ChartWorkspace {
  const [startAt, setStartAt] = useState(() => kstTodayLocalInput("09:00"));
  const [endAt, setEndAt] = useState(() => kstTodayLocalInput("15:30"));
  const [chartType, setChartType] = useState<"minute" | "daily">("minute");
  const [intervalMinutes, setIntervalMinutes] = useState(1);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [selection, setSelection] = useState<ChartSelection | null>(null);
  const [chartExpanded, setChartExpanded] = useState(true);

  const chartCandles = useMemo(
    () => (chart ? toChartCandles(chart.candles) : []),
    [chart],
  );
  const handleSelection = useCallback((next: ChartSelection) => {
    setSelection(next);
  }, []);

  const reset = useCallback(() => {
    setChart(null);
    setSelection(null);
  }, []);

  async function loadChart() {
    if (!security) return;
    setBusy(true);
    setSelection(null);
    const label = chartType === "daily" ? "일봉" : `${intervalMinutes}분봉`;
    setStatus(`Kiwoom ${label}을 조회하는 중입니다.`);
    try {
      const result = await loadChartApi({
        path: { symbol: security.symbol },
        query: {
          market: security.market,
          start_at: kstLocalInputToIso(startAt),
          end_at: kstLocalInputToIso(endAt),
          chart_type: chartType,
          interval_minutes: intervalMinutes,
        },
      });
      if (result.error || !result.data) {
        setStatus("차트 조회에 실패했습니다.");
        return;
      }
      setChart(result.data);
      setStatus(`${result.data.candles.length}개 ${label}을 불러왔습니다.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "차트 조회에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return {
    startAt,
    setStartAt,
    endAt,
    setEndAt,
    chartType,
    setChartType,
    intervalMinutes,
    setIntervalMinutes,
    chart,
    selection,
    chartExpanded,
    setChartExpanded,
    chartCandles,
    handleSelection,
    loadChart,
    reset,
  };
}
