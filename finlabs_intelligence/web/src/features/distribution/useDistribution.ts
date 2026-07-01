import { useCallback, useMemo, useState } from "react";

import {
  loadChart as loadChartApi,
  type CatalogItemResponse,
} from "../../shared/api";
import type { CandleResponse } from "../../api/generated/types.gen";
import { kstLocalInputToIso, kstTodayLocalInput } from "../chart/chartData";
import type { ChartSetupControls } from "../chart/chartSetup";
import type { ShapeMetric, TimeRange } from "./shapeMetrics";

interface Deps {
  readonly setStatus: (message: string) => void;
  readonly setBusy: (busy: boolean) => void;
}

// Stable per-security colors, reused by the basket chips and the overlaid
// histogram traces so a security reads the same hue everywhere on the page.
export const SECURITY_PALETTE = [
  "#6ee7b7",
  "#60a5fa",
  "#f472b6",
  "#fbbf24",
  "#a78bfa",
  "#fb7185",
  "#34d399",
  "#facc15",
] as const;

export function securityColor(index: number): string {
  return SECURITY_PALETTE[index % SECURITY_PALETTE.length];
}

export interface DistributionWorkspace extends ChartSetupControls {
  readonly basket: readonly CatalogItemResponse[];
  readonly addSecurity: (item: CatalogItemResponse) => void;
  readonly removeSecurity: (securityId: string) => void;
  readonly activeId: string | null;
  readonly setActiveId: (securityId: string) => void;
  readonly activeSecurity: CatalogItemResponse | null;
  readonly candlesBySecurity: Readonly<Record<string, readonly CandleResponse[]>>;
  readonly activeCandles: readonly CandleResponse[];
  readonly range: TimeRange | null;
  readonly setRange: (range: TimeRange | null) => void;
  readonly metric: ShapeMetric;
  readonly setMetric: (metric: ShapeMetric) => void;
  readonly loadCharts: () => Promise<void>;
  readonly reset: () => void;
}

export function useDistribution({ setStatus, setBusy }: Deps): DistributionWorkspace {
  const [startAt, setStartAt] = useState(() => kstTodayLocalInput("09:00"));
  const [endAt, setEndAt] = useState(() => kstTodayLocalInput("15:30"));
  const [chartType, setChartType] = useState<"minute" | "daily">("minute");
  const [intervalMinutes, setIntervalMinutes] = useState(1);

  const [basket, setBasket] = useState<readonly CatalogItemResponse[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [candlesBySecurity, setCandlesBySecurity] = useState<
    Record<string, readonly CandleResponse[]>
  >({});
  const [range, setRange] = useState<TimeRange | null>(null);
  const [metric, setMetric] = useState<ShapeMetric>("signed_body_ratio");

  const addSecurity = useCallback(
    (item: CatalogItemResponse) => {
      setBasket((current) =>
        current.some((entry) => entry.security_id === item.security_id)
          ? current
          : [...current, item],
      );
      setActiveIdState((current) => current ?? item.security_id);
      setStatus(`${item.display_name}을(를) 분석 대상에 추가했습니다.`);
    },
    [setStatus],
  );

  const removeSecurity = useCallback((securityId: string) => {
    setBasket((current) => current.filter((entry) => entry.security_id !== securityId));
    setCandlesBySecurity((current) => {
      const { [securityId]: _removed, ...rest } = current;
      return rest;
    });
    setActiveIdState((current) => (current === securityId ? null : current));
  }, []);

  const setActiveId = useCallback((securityId: string) => {
    setActiveIdState(securityId);
    // A different chart means the previous drag window no longer applies.
    setRange(null);
  }, []);

  const activeSecurity = useMemo(
    () => basket.find((entry) => entry.security_id === activeId) ?? null,
    [basket, activeId],
  );

  const activeCandles = useMemo(
    () => (activeId ? candlesBySecurity[activeId] ?? [] : []),
    [activeId, candlesBySecurity],
  );

  // Fetch every basket security over the shared query window in parallel, so
  // the distribution always reflects the same date range / bar unit across
  // securities. Partial failures are reported but never block the rest.
  const loadCharts = useCallback(async () => {
    if (basket.length === 0) {
      setStatus("먼저 분석할 종목을 추가하세요.");
      return;
    }
    setBusy(true);
    setRange(null);
    const label = chartType === "daily" ? "일봉" : `${intervalMinutes}분봉`;
    setStatus(`${basket.length}개 종목의 ${label}을 조회하는 중입니다.`);

    let startIso: string;
    let endIso: string;
    try {
      startIso = kstLocalInputToIso(startAt);
      endIso = kstLocalInputToIso(endAt);
    } catch {
      setBusy(false);
      setStatus("조회 시작과 종료를 분 단위까지 입력하세요.");
      return;
    }

    const results = await Promise.all(
      basket.map(async (security) => {
        try {
          const result = await loadChartApi({
            path: { symbol: security.symbol },
            query: {
              market: security.market,
              start_at: startIso,
              end_at: endIso,
              chart_type: chartType,
              interval_minutes: intervalMinutes,
            },
          });
          if (result.error || !result.data) return { security, candles: null };
          return { security, candles: result.data.candles };
        } catch {
          return { security, candles: null };
        }
      }),
    );

    const loaded: Record<string, readonly CandleResponse[]> = {};
    const failed: string[] = [];
    let total = 0;
    for (const { security, candles } of results) {
      if (candles) {
        loaded[security.security_id] = candles;
        total += candles.length;
      } else {
        failed.push(security.display_name);
      }
    }
    setCandlesBySecurity(loaded);
    setActiveIdState((current) =>
      current && loaded[current] ? current : (Object.keys(loaded)[0] ?? null),
    );
    setBusy(false);
    setStatus(
      failed.length
        ? `${total}개 캔들을 불러왔습니다. 실패: ${failed.join(", ")}`
        : `${total}개 캔들을 불러왔습니다.`,
    );
  }, [basket, chartType, intervalMinutes, startAt, endAt, setBusy, setStatus]);

  const reset = useCallback(() => {
    setBasket([]);
    setActiveIdState(null);
    setCandlesBySecurity({});
    setRange(null);
  }, []);

  return {
    startAt,
    setStartAt,
    endAt,
    setEndAt,
    chartType,
    setChartType,
    intervalMinutes,
    setIntervalMinutes,
    basket,
    addSecurity,
    removeSecurity,
    activeId,
    setActiveId,
    activeSecurity,
    candlesBySecurity,
    activeCandles,
    range,
    setRange,
    metric,
    setMetric,
    loadCharts,
    reset,
  };
}
