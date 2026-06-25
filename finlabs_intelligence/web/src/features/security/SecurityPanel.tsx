import type { CatalogItemResponse } from "../../shared/api";
import type { CatalogSearch } from "./useCatalogSearch";

interface SecurityPanelProps {
  readonly search: CatalogSearch;
  readonly security: CatalogItemResponse | null;
  readonly busy: boolean;
  readonly onSelect: (item: CatalogItemResponse) => void;
}

export function SecurityPanel({
  search,
  security,
  busy,
  onSelect,
}: SecurityPanelProps) {
  const { query, setQuery, catalog } = search;
  return (
    <aside
      className="panel search-panel min-h-0 lg:h-full"
      aria-labelledby="security-search"
    >
      <div>
        <span className="step">01</span>
        <h2 id="security-search">국내 종목 선택</h2>
      </div>
      <form className="search-form" onSubmit={search.search}>
        <input
          aria-label="종목명 또는 종목코드"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="예: 삼성전자 또는 005930"
          required
          value={query}
        />
        <button disabled={busy} type="submit">검색</button>
      </form>
      <div className="catalog-results">
        {catalog.map((item) => (
          <button
            className={security?.security_id === item.security_id ? "security selected" : "security"}
            key={item.security_id}
            onClick={() => onSelect(item)}
            type="button"
          >
            <strong>{item.display_name}</strong>
            <span>{item.market} · {item.symbol}</span>
          </button>
        ))}
      </div>
      {catalog[0] ? (
        <p className="catalog-provenance">
          {catalog[0].catalog_stale ? "⚠ 오래된 " : ""}임시 종목원: {catalog[0].catalog_source} · 수집 시각 {catalog[0].catalog_acquired_at} · 현재 명칭만 보장 · 스냅샷 {catalog[0].catalog_snapshot_id}
        </p>
      ) : null}
    </aside>
  );
}
