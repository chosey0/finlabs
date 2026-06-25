import type { CatalogItemResponse } from "../../shared/api";
import { CandleChart } from "./CandleChart";
import { formatKstTimestamp } from "./chartData";
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
    chartExpanded,
    setChartExpanded,
    chart: chartData,
    chartCandles,
    selection,
    handleSelection,
  } = chart;
  return (
    <section className="panel chart-panel" aria-labelledby="chart-heading">
      <div className={chartExpanded ? "chart-heading expanded" : "chart-heading"}>
        <div>
          <span className="step">02</span>
          <h2 id="chart-heading">
            <button
              aria-controls="chart-accordion-content"
              aria-expanded={chartExpanded}
              className="accordion-toggle"
              onClick={() => setChartExpanded((current) => !current)}
              type="button"
            >
              차트 관측 시점
              <span aria-hidden="true" className="accordion-icon">{chartExpanded ? "−" : "+"}</span>
            </button>
          </h2>
        </div>
        <div className="range-controls">
          <div className="control-group">
            <span className="control-group-label">차트 설정</span>
            <div className="control-group-fields">
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
            </div>
          </div>
          <div className="control-group">
            <span className="control-group-label">조회 기간</span>
            <div className="control-group-fields">
              <label>시작 <input onChange={(event) => setStartAt(event.target.value)} type="datetime-local" value={startAt} /></label>
              <label>종료 <input onChange={(event) => setEndAt(event.target.value)} type="datetime-local" value={endAt} /></label>
            </div>
          </div>
          <div className="chart-actions">
            <button disabled={!security || busy} onClick={onLoadChart} type="button">차트 불러오기</button>
            <button disabled={!selection || !security || busy} onClick={onDiscover} type="button">
              선택 구간 뉴스 검색
            </button>
          </div>
        </div>
      </div>
      <div className="accordion-content" hidden={!chartExpanded} id="chart-accordion-content">
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
      <output
        aria-live="polite"
        className={selection ? "selection active" : "selection"}
        data-testid="selected-candle"
      >
        {selection ? (
          <>
            <span>뉴스 검색 구간 · KST · 양끝 포함</span>
            <strong>{formatKstTimestamp(selection.windowStart)} — {formatKstTimestamp(selection.windowEnd)}</strong>
          </>
        ) : "캔들을 클릭하면 직전 1시간의 뉴스 검색 구간을 확정합니다."}
      </output>
    </section>
  );
}
