import { formatKstTimestamp } from "./chartData";
import type { ChartSelection } from "./chartSelection";

interface SelectionBridgeProps {
  readonly selection: ChartSelection | null;
}

// Signature element: a horizontal band that ties the selected candle's window to
// the t0 reaction anchor, making the tool's core idea (news at t0 -> 30-minute
// market reaction) visible between the chart and the news panes.
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
            <span aria-hidden="true" className="bridge-line" />
            <span className="bridge-anchor">t0</span>
            <span aria-hidden="true" className="bridge-line" />
            <time className="bridge-time">{formatKstTimestamp(selection.windowEnd)}</time>
            <span className="bridge-reaction">반응 30거래분 ▸</span>
          </div>
        </>
      ) : (
        <span className="bridge-empty">
          캔들을 클릭하면 직전 1시간이 뉴스 검색 구간으로, 종료 시점이 반응 라벨 앵커(t0)로 확정됩니다.
        </span>
      )}
    </div>
  );
}
