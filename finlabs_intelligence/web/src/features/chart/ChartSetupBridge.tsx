import type { CatalogItemResponse } from "../../shared/api";
import type { ChartWorkspace } from "./useChart";

const MINUTE_INTERVALS = [1, 3, 5, 10, 15, 30, 45, 60] as const;

interface ChartSetupBridgeProps {
  readonly chart: ChartWorkspace;
  readonly security: CatalogItemResponse | null;
  readonly busy: boolean;
  readonly onLoadChart: () => void;
}

// Chart query controls, shaped as a bridge that sits to the left of the news
// selection bridge. This picks *which candles to fetch* (the chart's date
// range) — distinct from the news window/t0, which is chosen on the selection
// bridge once candles are loaded.
export function ChartSetupBridge({
  chart,
  security,
  busy,
  onLoadChart,
}: ChartSetupBridgeProps) {
  const {
    startAt,
    setStartAt,
    endAt,
    setEndAt,
    chartType,
    setChartType,
    intervalMinutes,
    setIntervalMinutes,
  } = chart;

  return (
    <div className="bridge chart-setup" aria-label="차트 조회">
      <span className="bridge-label">차트 조회</span>
      <div className="chart-setup-fields">
        <label className="bridge-edit-field">
          차트
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
          <label className="bridge-edit-field">
            단위
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
        <label className="bridge-edit-field">
          조회 시작
          <input
            aria-label="조회 시작"
            onChange={(event) => setStartAt(event.target.value)}
            type="datetime-local"
            value={startAt}
          />
        </label>
        <span aria-hidden="true" className="bridge-edit-sep">→</span>
        <label className="bridge-edit-field">
          조회 종료
          <input
            aria-label="조회 종료"
            onChange={(event) => setEndAt(event.target.value)}
            type="datetime-local"
            value={endAt}
          />
        </label>
        <button
          className="chart-setup-load"
          disabled={!security || busy}
          onClick={onLoadChart}
          type="button"
        >차트 불러오기</button>
      </div>
    </div>
  );
}
