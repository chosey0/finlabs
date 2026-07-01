import { lazy, Suspense, useEffect, useState } from "react";

import { NewsWorkbenchPage } from "./NewsWorkbenchPage";
import type { WorkbenchRoute } from "./WorkbenchNav";

// Plotly is heavy and only the distribution page needs it, so this route is
// code-split: the Plotly chunk loads on demand when the analyst opens it,
// keeping the default news workbench's initial bundle lean.
const DistributionWorkbenchPage = lazy(() =>
  import("./DistributionWorkbenchPage").then((module) => ({
    default: module.DistributionWorkbenchPage,
  })),
);

// Minimal hash router — no dependency, shareable URLs, and survives reload.
// The empty/`#/` route stays the news workbench so existing entry points and
// the layout tests keep landing on the same page.
function routeFromHash(): WorkbenchRoute {
  return window.location.hash.replace(/^#/, "") === "/distribution"
    ? "distribution"
    : "news";
}

export function App() {
  const [route, setRoute] = useState<WorkbenchRoute>(routeFromHash);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  if (route === "distribution") {
    return (
      <Suspense fallback={<main className="app"><p className="status">분포 워크벤치를 불러오는 중…</p></main>}>
        <DistributionWorkbenchPage />
      </Suspense>
    );
  }
  return <NewsWorkbenchPage />;
}
