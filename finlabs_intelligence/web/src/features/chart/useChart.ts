import { useCallback, useMemo, useState } from "react";
import type { UTCTimestamp } from "lightweight-charts";

import { loadChart as loadChartApi, type CatalogItemResponse, type ChartResponse } from "../../shared/api";
import type { IndicatorKind, IndicatorSeries } from "./CandleChart";
import {
  formatKstTimestamp,
  kstLocalInputToIso,
  kstLocalInputToUnix,
  kstTodayLocalInput,
  kstUnixToLocalInput,
  toChartCandles,
  toTurnoverHistogram,
  toVolumeHistogram,
} from "./chartData";
import type { ChartSelection } from "./chartSelection";
import { selectWindow } from "./chartSelection";
import type { ChartSetupControls } from "./chartSetup";
import type { ReactionBand } from "./reactionHighlight";
import { reactionWindowEnd } from "./reactionWindow";

export type IndicatorChoice = IndicatorKind | "none";

interface Deps {
  readonly security: CatalogItemResponse | null;
  readonly setStatus: (message: string) => void;
  readonly setBusy: (busy: boolean) => void;
}

export interface ChartWorkspace extends ChartSetupControls {
  readonly chart: ChartResponse | null;
  readonly selection: ChartSelection | null;
  readonly chartCandles: ReturnType<typeof toChartCandles>;
  readonly indicator: IndicatorChoice;
  readonly setIndicator: (value: IndicatorChoice) => void;
  readonly indicatorSeries: IndicatorSeries | null;
  readonly reactionBand: ReactionBand | null;
  readonly handleSelection: (next: ChartSelection) => void;
  readonly windowStartInput: string;
  readonly setWindowStartInput: (value: string) => void;
  readonly windowEndInput: string;
  readonly setWindowEndInput: (value: string) => void;
  readonly applyManualWindow: () => void;
  readonly loadChart: () => Promise<void>;
  readonly reset: () => void;
}

export function useChart({ security, setStatus, setBusy }: Deps): ChartWorkspace {
  // 기본 조회 구간은 한국 정규장(09:00~15:30 KST). 애널리스트가 페이지를 열자마자
  // 오늘 정규장 전체를 조회하도록 오늘 날짜로 초기화한다.
  const [startAt, setStartAt] = useState(() => kstTodayLocalInput("09:00"));
  const [endAt, setEndAt] = useState(() => kstTodayLocalInput("15:30"));
  const [chartType, setChartType] = useState<"minute" | "daily">("minute");
  const [intervalMinutes, setIntervalMinutes] = useState(1);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [selection, setSelection] = useState<ChartSelection | null>(null);
  const [windowStartInput, setWindowStartInput] = useState("");
  const [windowEndInput, setWindowEndInput] = useState("");
  const [indicator, setIndicator] = useState<IndicatorChoice>("volume");

  const chartCandles = useMemo(
    () => (chart ? toChartCandles(chart.candles) : []),
    [chart],
  );
  const indicatorSeries = useMemo<IndicatorSeries | null>(() => {
    if (!chart || indicator === "none") return null;
    const data =
      indicator === "turnover"
        ? toTurnoverHistogram(chart.candles)
        : toVolumeHistogram(chart.candles);
    return { kind: indicator, data };
  }, [chart, indicator]);
  // 선택한 t0에서 시작하는 30거래분 반응 윈도를 파생한다. 끝 시각은 벽시계 30분이
  // 아니라 reactionWindowEnd가 장 마감·휴장을 건너뛰며 계산한 거래분 기준이다.
  const reactionBand = useMemo<ReactionBand | null>(() => {
    if (!selection) return null;
    return {
      from: selection.selectedAt as UTCTimestamp,
      to: reactionWindowEnd(selection.selectedAt) as UTCTimestamp,
    };
  }, [selection]);
  // A candle click also fills the manual inputs, so the two entry paths share
  // one source of truth and the analyst can fine-tune a clicked window by hand.
  const handleSelection = useCallback((next: ChartSelection) => {
    setSelection(next);
    setWindowStartInput(kstUnixToLocalInput(next.windowStart));
    setWindowEndInput(kstUnixToLocalInput(next.windowEnd));
  }, []);

  const applyManualWindow = useCallback(() => {
    let start: number;
    let end: number;
    try {
      start = kstLocalInputToUnix(windowStartInput);
      end = kstLocalInputToUnix(windowEndInput);
    } catch {
      setStatus("뉴스 구간의 시작과 끝(t0)을 분 단위까지 입력하세요.");
      return;
    }
    if (start >= end) {
      setStatus("뉴스 구간의 시작은 끝(t0)보다 앞서야 합니다.");
      return;
    }
    setSelection(selectWindow(start, end));
    setStatus(`뉴스 구간을 직접 설정했습니다. t0 ${formatKstTimestamp(end)}`);
  }, [windowStartInput, windowEndInput, setStatus]);

  const reset = useCallback(() => {
    setChart(null);
    setSelection(null);
  }, []);

  async function loadChart() {
    if (!security) return;
    setBusy(true);
    // 이전 종목/구간에서 찍은 t0 선택은 새 캔들 위에서 의미가 없으므로 조회 시작 시
    // 즉시 비운다(오래된 반응 윈도가 잘못된 종목에 남는 것을 방지).
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
    chartCandles,
    indicator,
    setIndicator,
    indicatorSeries,
    reactionBand,
    handleSelection,
    windowStartInput,
    setWindowStartInput,
    windowEndInput,
    setWindowEndInput,
    applyManualWindow,
    loadChart,
    reset,
  };
}
