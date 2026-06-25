import type { FormEvent } from "react";

import { formatKstTimestamp } from "./chartData";
import type { ChartSelection } from "./chartSelection";

interface SelectionBridgeProps {
  readonly selection: ChartSelection | null;
  readonly windowStartInput: string;
  readonly windowEndInput: string;
  readonly onWindowStartChange: (value: string) => void;
  readonly onWindowEndChange: (value: string) => void;
  readonly onApply: () => void;
  readonly busy: boolean;
}

// Signature element. The selected candle is t0: the news search window is the
// span *before* it (past, the data we have), and the reaction label window is
// the 30 trading minutes *after* it (future, the market's response). The bridge
// draws that two-phase timeline pivoting on t0, and doubles as the control
// surface — the analyst can click a candle or type the window's two ends here.
export function SelectionBridge({
  selection,
  windowStartInput,
  windowEndInput,
  onWindowStartChange,
  onWindowEndChange,
  onApply,
  busy,
}: SelectionBridgeProps) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onApply();
  }

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
              <span className="bridge-seg-cap">검색 구간</span>
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
          캔들을 클릭하거나 아래에 직접 입력해 뉴스 검색 구간과 t0를 지정하세요.
        </span>
      )}
      <form className="bridge-edit" onSubmit={handleSubmit}>
        <span className="bridge-edit-label">직접 입력</span>
        <label className="bridge-edit-field">
          시작
          <input
            aria-label="뉴스 구간 시작"
            onChange={(event) => onWindowStartChange(event.target.value)}
            type="datetime-local"
            value={windowStartInput}
          />
        </label>
        <span aria-hidden="true" className="bridge-edit-sep">→</span>
        <label className="bridge-edit-field">
          끝 · t0
          <input
            aria-label="뉴스 구간 끝 t0"
            onChange={(event) => onWindowEndChange(event.target.value)}
            type="datetime-local"
            value={windowEndInput}
          />
        </label>
        <button disabled={busy} type="submit">구간 적용</button>
      </form>
    </div>
  );
}
