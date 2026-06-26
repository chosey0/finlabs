import type { FormEvent } from "react";

import type { CatalogItemResponse } from "../../shared/api";
import type { ChartSelection } from "./chartSelection";
import { describeNewsWindow } from "./newsWindow";

interface SelectionBridgeProps {
  readonly selection: ChartSelection | null;
  readonly security: CatalogItemResponse | null;
  readonly windowStartInput: string;
  readonly windowEndInput: string;
  readonly onWindowStartChange: (value: string) => void;
  readonly onWindowEndChange: (value: string) => void;
  readonly onApply: () => void;
  readonly onDiscover: () => void;
  readonly busy: boolean;
}

// Signature element. t0 is the news reaction anchor; the news search window is
// the real *time* span before it. The card spells that out — direction, basis,
// and the concrete start/end instants — so "직전 60분" can't be mistaken for a
// bar count. It doubles as the control surface: click a candle or type the two
// ends here.
export function SelectionBridge({
  selection,
  security,
  windowStartInput,
  windowEndInput,
  onWindowStartChange,
  onWindowEndChange,
  onApply,
  onDiscover,
  busy,
}: SelectionBridgeProps) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onApply();
  }

  const facts = selection ? describeNewsWindow(selection) : null;

  return (
    <div
      aria-live="polite"
      className={selection ? "bridge selection-bridge active" : "bridge selection-bridge"}
      data-testid="selected-candle"
    >
      {facts ? (
        <>
          <div className="window-head">
            <span className="bridge-label">뉴스 검색 구간</span>
            <span
              className={
                facts.source === "manual"
                  ? "window-source window-source--manual"
                  : "window-source"
              }
            >
              {facts.sourceLabel}
            </span>
          </div>
          <dl className="window-facts">
            <div>
              <dt>기준 캔들 t0</dt>
              <dd className="window-t0">{facts.t0Label}</dd>
            </div>
            <div>
              <dt>검색 방향</dt>
              <dd>{facts.directionLabel} 뉴스 검색</dd>
            </div>
            <div>
              <dt>검색 기준</dt>
              <dd>{facts.basisLabel}</dd>
            </div>
            <div>
              <dt>실제 시간 범위</dt>
              <dd className="window-range">
                {facts.rangeStartLabel} ~ {facts.rangeEndLabel}
              </dd>
            </div>
            <div>
              <dt>시간대</dt>
              <dd>{facts.timezoneLabel}</dd>
            </div>
          </dl>
        </>
      ) : (
        <span className="bridge-empty">
          기준 캔들을 선택하면 뉴스 검색 구간이 표시됩니다.
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
        <button
          className="bridge-discover"
          disabled={!selection || !security || busy}
          onClick={onDiscover}
          type="button"
        >선택 구간 뉴스 검색</button>
      </form>
    </div>
  );
}
