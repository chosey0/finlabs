import { useState, type FormEvent } from "react";

import type { CatalogItemResponse } from "../../shared/api";
import type { CatalogSearch } from "./useCatalogSearch";

interface SearchBarProps {
  readonly search: CatalogSearch;
  readonly security: CatalogItemResponse | null;
  readonly busy: boolean;
  readonly onSelect: (item: CatalogItemResponse) => void;
}

// Command-bar search that lives in the top bar. Results drop down beneath the
// input and close once a security is chosen, so the two-pane workbench below
// stays clear.
export function SearchBar({ search, security, busy, onSelect }: SearchBarProps) {
  const { query, setQuery, catalog } = search;
  const [open, setOpen] = useState(false);

  async function handleSubmit(event: FormEvent) {
    await search.search(event);
    setOpen(true);
  }

  function handleSelect(item: CatalogItemResponse) {
    onSelect(item);
    setOpen(false);
  }

  return (
    <div className="searchbar" role="search">
      <form className="search-form" onSubmit={handleSubmit} aria-label="국내 종목 선택">
        <input
          aria-label="종목명 또는 종목코드"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="종목명 또는 종목코드"
          required
          value={query}
        />
        <button disabled={busy} type="submit">검색</button>
      </form>
      {security ? (
        <span className="security-chip">
          <strong>{security.display_name}</strong>
          <span>{security.market} · {security.symbol}</span>
        </span>
      ) : null}
      {open && catalog.length > 0 ? (
        <div className="search-results" role="listbox" aria-label="검색 결과">
          {catalog.map((item) => (
            <button
              className={security?.security_id === item.security_id ? "security selected" : "security"}
              key={item.security_id}
              onClick={() => handleSelect(item)}
              type="button"
            >
              <strong>{item.display_name}</strong>
              <span>{item.market} · {item.symbol}</span>
            </button>
          ))}
          {catalog[0] ? (
            <p className="catalog-provenance">
              {catalog[0].catalog_stale ? "⚠ 오래된 " : ""}임시 종목원: {catalog[0].catalog_source} · 수집 {catalog[0].catalog_acquired_at} · 현재 명칭만 보장
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
