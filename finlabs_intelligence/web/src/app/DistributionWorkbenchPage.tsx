import { useMemo, useState } from "react";

import { toChartCandles } from "../features/chart/chartData";
import { ChartSetupBridge } from "../features/chart/ChartSetupBridge";
import { DistributionCandleChart } from "../features/distribution/DistributionCandleChart";
import { DistributionPanel } from "../features/distribution/DistributionPanel";
import { SecurityBasket } from "../features/distribution/SecurityBasket";
import { useDistribution } from "../features/distribution/useDistribution";
import { SearchBar } from "../features/security/SearchBar";
import { useCatalogSearch } from "../features/security/useCatalogSearch";
import type { CatalogItemResponse } from "../shared/api";
import { WorkbenchNav } from "./WorkbenchNav";

// Shape-distribution workbench. Reuses the news page's command-bar header and
// the chart-setup bridge, but drops the news-window bridge: here the left pane
// is a drag-selectable chart and the right pane renders Plotly distributions of
// the per-candle shape metrics over the selected (or full) window.
export function DistributionWorkbenchPage() {
  const [status, setStatus] = useState("분석할 종목을 검색해 추가하세요.");
  const [busy, setBusy] = useState(false);

  const search = useCatalogSearch({ setStatus, setBusy });
  const distribution = useDistribution({ setStatus, setBusy });

  function handleAddSecurity(item: CatalogItemResponse) {
    distribution.addSecurity(item);
  }

  const candles = useMemo(
    () => toChartCandles(distribution.activeCandles),
    [distribution.activeCandles],
  );

  const active = distribution.activeSecurity;
  const identity = active ? `${active.display_name} ${active.symbol}` : "차트";
  const intervalLabel =
    distribution.chartType === "daily" ? "일봉" : `${distribution.intervalMinutes}분봉`;
  const meta = active ? `${active.market} · ${intervalLabel}` : null;

  // The button that adds to the basket should enable as soon as a security can
  // be loaded; the bridge only reads `security` to toggle that disabled state.
  const bridgeSecurity = distribution.activeSecurity ?? distribution.basket[0] ?? null;

  return (
    <main className="app">
      <header className="commandbar">
        <p className="eyebrow">FINLABS · LOCAL DATA WORKBENCH</p>
        <WorkbenchNav active="distribution" />
        <SearchBar
          search={search}
          security={distribution.activeSecurity}
          busy={busy}
          onSelect={handleAddSecurity}
        />
      </header>

      <div className="bridge-row">
        <ChartSetupBridge
          chart={distribution}
          security={bridgeSecurity}
          busy={busy}
          onLoadChart={() => void distribution.loadCharts()}
        />
        <SecurityBasket
          basket={distribution.basket}
          activeId={distribution.activeId}
          onActivate={distribution.setActiveId}
          onRemove={distribution.removeSecurity}
        />
      </div>

      <div className="workbench" data-testid="workspace-columns">
        <section aria-label="차트" className="pane chart-pane">
          <header className="pane-head">
            <h2 className="chart-title">
              {active ? (
                <>
                  {identity}
                  <span className="chart-title-meta"> · {meta}</span>
                </>
              ) : (
                "차트"
              )}
            </h2>
            <button
              className="range-reset"
              disabled={!distribution.range}
              onClick={() => distribution.setRange(null)}
              type="button"
            >전체 구간</button>
          </header>
          <div className="pane-body">
            {candles.length ? (
              <>
                <p className="chart-hint">
                  드래그해서 분포를 확인할 구간을 지정하세요. 지정하지 않으면 전체 캔들을 사용합니다.
                </p>
                <DistributionCandleChart
                  candles={candles}
                  range={distribution.range}
                  onSelectRange={distribution.setRange}
                />
              </>
            ) : (
              <div className="chart-empty">
                종목을 추가하고 차트를 불러오면 캔들을 표시합니다.
              </div>
            )}
          </div>
        </section>

        <DistributionPanel distribution={distribution} />
      </div>

      <footer className="statusbar">
        <p aria-atomic="true" aria-live="polite" className="status" role="status">{status}</p>
      </footer>
    </main>
  );
}
