import { formatKstTimestamp } from "./chartData";
import type { ChartSelection } from "./chartSelection";

interface SelectionBridgeProps {
  readonly selection: ChartSelection | null;
}

// Signature element. The selected candle is t0: the news search window is the
// hour *before* it (past, the data we have), and the reaction label window is the
// 30 trading minutes *after* it (future, the market's response). The bridge draws
// that two-phase timeline pivoting on t0, so the tool's core idea is visible
// between the chart and news panes.
export function SelectionBridge({ selection }: SelectionBridgeProps) {
  return (
    <div
      aria-live="polite"
      className={selection ? "bridge active" : "bridge"}
      data-testid="selected-candle"
    >
      {selection ? (
        <>
          <span className="bridge-label">뉴스 검색 구간 · KST · 양끝 포함</span>
          <div className="bridge-track">
            <time className="bridge-time">{formatKstTimestamp(selection.windowStart)}</time>
            <span className="bridge-seg bridge-seg--search">
              <span className="bridge-rule" />
              <span className="bridge-seg-cap">직전 1시간</span>
              <span className="bridge-rule" />
            </span>
            <span aria-hidden="true" className="bridge-node" />
            <span className="bridge-anchor">t0</span>
            <time className="bridge-time bridge-time--t0">{formatKstTimestamp(selection.windowEnd)}</time>
            <span className="bridge-seg bridge-seg--reaction">
              <span className="bridge-seg-cap bridge-seg-cap--reaction">반응 30거래분</span>
              <span className="bridge-rule bridge-rule--reaction" />
              <span aria-hidden="true" className="bridge-arrow">▸</span>
            </span>
          </div>
        </>
      ) : (
        <span className="bridge-empty">
          캔들을 클릭하면 직전 1시간이 뉴스 검색 구간으로, 그 시점(t0)이 반응 라벨 앵커로 확정됩니다.
        </span>
      )}
    </div>
  );
}
