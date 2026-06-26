import type { CatalogItemResponse } from "../../shared/api";
import { CandleChart } from "./CandleChart";
import type { ChartWorkspace } from "./useChart";

interface ChartPanelProps {
  readonly chart: ChartWorkspace;
  readonly security: CatalogItemResponse | null;
}

export function ChartPanel({ chart, security }: ChartPanelProps) {
  const {
    chartType,
    intervalMinutes,
    indicator,
    setIndicator,
    indicatorSeries,
    reactionBand,
    chart: chartData,
    chartCandles,
    selection,
    handleSelection,
  } = chart;

  // Identity headline: which security/bar unit the chart is showing.
  const identity = [security?.display_name, security?.symbol]
    .filter(Boolean)
    .join(" ");
  const intervalLabel = chartType === "daily" ? "일봉" : `${intervalMinutes}분봉`;
  const meta = [security?.market, intervalLabel].filter(Boolean).join(" · ");

  return (
    <section className="pane chart-pane" aria-label="차트">
      <header className="pane-head">
        <h2 className="chart-title">
          {identity ? (
            <>
              {identity}
              <span className="chart-title-meta"> · {meta}</span>
            </>
          ) : (
            "차트"
          )}
        </h2>
        <label className="chart-indicator">보조지표
          <select
            aria-label="보조지표"
            onChange={(event) => setIndicator(event.target.value as typeof indicator)}
            value={indicator}
          >
            <option value="volume">거래량</option>
            <option value="turnover">거래대금</option>
            <option value="none">끄기</option>
          </select>
        </label>
      </header>
      <div className="pane-body">
        {chartData ? (
          <CandleChart
            candles={chartCandles}
            indicator={indicatorSeries}
            reaction={reactionBand}
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
