import { useState } from "react";

import { ChartPanel } from "../features/chart/ChartPanel";
import { useChart } from "../features/chart/useChart";
import { NewsPanel } from "../features/labeling/NewsPanel";
import { useLabeling } from "../features/labeling/useLabeling";
import { SecurityPanel } from "../features/security/SecurityPanel";
import { useCatalogSearch } from "../features/security/useCatalogSearch";
import type { CatalogItemResponse } from "../shared/api";

// Composition root: owns the cross-feature shared state (selected security,
// status line, busy flag) and orchestrates the workflow resets. Each feature
// owns its own state and async actions through its hook.
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
    <main className="workspace h-[100dvh] overflow-hidden">
      <header className="shrink-0">
        <p className="eyebrow">FINLABS · LOCAL DATA WORKBENCH</p>
      </header>

      <p aria-atomic="true" aria-live="polite" className="status" role="status">{status}</p>

      <div
        className="grid min-h-0 flex-1 items-start gap-5 max-lg:overflow-y-auto lg:grid-cols-[18rem_minmax(0,1fr)] lg:overflow-hidden"
        data-testid="workspace-columns"
      >
        <SecurityPanel
          search={search}
          security={security}
          busy={busy}
          onSelect={handleSelectSecurity}
        />

        <div className="analysis-layout min-h-0 min-w-0 lg:h-full" data-testid="work-area">
          <ChartPanel
            chart={chart}
            security={security}
            busy={busy}
            onLoadChart={handleLoadChart}
            onDiscover={handleDiscover}
          />
          <NewsPanel labeling={labeling} busy={busy} />
        </div>
      </div>
    </main>
  );
}
