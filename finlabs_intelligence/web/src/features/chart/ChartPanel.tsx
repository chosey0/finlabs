import type { CatalogItemResponse } from "../../shared/api";
import { CandleChart } from "./CandleChart";
import type { ChartWorkspace } from "./useChart";

const MINUTE_INTERVALS = [1, 3, 5, 10, 15, 30, 45, 60] as const;

interface ChartPanelProps {
  readonly chart: ChartWorkspace;
  readonly security: CatalogItemResponse | null;
  readonly busy: boolean;
  readonly onLoadChart: () => void;
  readonly onDiscover: () => void;
}

export function ChartPanel({
  chart,
  security,
  busy,
  onLoadChart,
  onDiscover,
}: ChartPanelProps) {
  const {
    startAt,
    setStartAt,
    endAt,
    setEndAt,
    chartType,
    setChartType,
    intervalMinutes,
    setIntervalMinutes,
    chart: chartData,
    chartCandles,
    selection,
    handleSelection,
  } = chart;
  return (
    <section className="pane chart-pane" aria-label="차트">
      <header className="pane-head">
        <h2>차트</h2>
        <div className="control-row">
          <label>차트
            <select
              aria-label="차트 종류"
              onChange={(event) => setChartType(event.target.value as "minute" | "daily")}
              value={chartType}
            >
              <option value="minute">분봉</option>
              <option value="daily">일봉</option>
            </select>
          </label>
          {chartType === "minute" ? (
            <label>분 단위
              <select
                aria-label="분봉 단위"
                onChange={(event) => setIntervalMinutes(Number(event.target.value))}
                value={intervalMinutes}
              >
                {MINUTE_INTERVALS.map((minutes) => (
                  <option key={minutes} value={minutes}>{minutes}분</option>
                ))}
              </select>
            </label>
          ) : null}
          <label>시작 <input onChange={(event) => setStartAt(event.target.value)} type="datetime-local" value={startAt} /></label>
          <label>종료 <input onChange={(event) => setEndAt(event.target.value)} type="datetime-local" value={endAt} /></label>
          <div className="chart-actions">
            <button disabled={!security || busy} onClick={onLoadChart} type="button">차트 불러오기</button>
            <button disabled={!selection || !security || busy} onClick={onDiscover} type="button">
              선택 구간 뉴스 검색
            </button>
          </div>
        </div>
      </header>
      <div className="pane-body">
        {chartData ? (
          <CandleChart
            candles={chartCandles}
            onSelect={handleSelection}
            selectedAt={selection?.selectedAt ?? null}
          />
        ) : (
          <div className="chart-empty">종목과 조회 범위를 선택하면 Kiwoom 차트를 표시합니다.</div>
        )}
      </div>
    </section>
  );
}
