import { useState } from "react";

import { ChartPanel } from "../features/chart/ChartPanel";
import { SelectionBridge } from "../features/chart/SelectionBridge";
import { useChart } from "../features/chart/useChart";
import { DatasetControls } from "../features/labeling/DatasetControls";
import { NewsPanel } from "../features/labeling/NewsPanel";
import { useLabeling } from "../features/labeling/useLabeling";
import { SearchBar } from "../features/security/SearchBar";
import { useCatalogSearch } from "../features/security/useCatalogSearch";
import type { CatalogItemResponse } from "../shared/api";

// Composition root. Top to bottom: a command bar (search), the selection bridge
// (signature), the two-pane workbench (chart | news always co-visible), and a
// footer that carries dataset export and the status line. App owns the
// cross-feature shared state and orchestrates the workflow resets.
export function App() {
  const [security, setSecurity] = useState<CatalogItemResponse | null>(null);
  const [status, setStatus] = useState("종목을 검색하세요.");
  const [busy, setBusy] = useState(false);

  const search = useCatalogSearch({ setStatus, setBusy });
  const chart = useChart({ security, setStatus, setBusy });
  const labeling = useLabeling({ security, setStatus, setBusy });

  function handleSelectSecurity(item: CatalogItemResponse) {
    setSecurity(item);
    chart.reset();
    labeling.reset();
    setStatus(`${item.display_name}을 선택했습니다.`);
  }

  async function handleLoadChart() {
    labeling.reset();
    await chart.loadChart();
  }

  function handleDiscover() {
    void labeling.discoverNews(chart.selection);
  }

  return (
    <main className="app">
      <header className="commandbar">
        <p className="eyebrow">FINLABS · LOCAL DATA WORKBENCH</p>
        <SearchBar
          search={search}
          security={security}
          busy={busy}
          onSelect={handleSelectSecurity}
        />
      </header>

      <SelectionBridge
        selection={chart.selection}
        windowStartInput={chart.windowStartInput}
        windowEndInput={chart.windowEndInput}
        onWindowStartChange={chart.setWindowStartInput}
        onWindowEndChange={chart.setWindowEndInput}
        onApply={chart.applyManualWindow}
        busy={busy}
      />

      <div className="workbench" data-testid="workspace-columns">
        <ChartPanel
          chart={chart}
          security={security}
          busy={busy}
          onLoadChart={handleLoadChart}
          onDiscover={handleDiscover}
        />
        <NewsPanel labeling={labeling} busy={busy} />
      </div>

      <footer className="statusbar">
        <DatasetControls
          selectedSinks={labeling.selectedSinks}
          setSelectedSinks={labeling.setSelectedSinks}
          busy={busy}
          onFreeze={labeling.freeze}
          datasetResult={labeling.datasetResult}
          exportResult={labeling.exportResult}
        />
        <p aria-atomic="true" aria-live="polite" className="status" role="status">{status}</p>
      </footer>
    </main>
  );
}
