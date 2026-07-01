export type WorkbenchRoute = "news" | "distribution";

// Hash-based tabs shared by both workbench headers. Anchors (not buttons) so the
// route is shareable and survives reload, and so they never register as the
// level-1 heading the layout tests forbid.
export function WorkbenchNav({ active }: { active: WorkbenchRoute }) {
  return (
    <nav aria-label="워크벤치 전환" className="workbench-nav">
      <a className={active === "news" ? "nav-link active" : "nav-link"} href="#/">
        뉴스 수집
      </a>
      <a
        className={active === "distribution" ? "nav-link active" : "nav-link"}
        href="#/distribution"
      >
        형태 분포
      </a>
    </nav>
  );
}
