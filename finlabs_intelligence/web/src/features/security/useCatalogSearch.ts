import { useState, type FormEvent } from "react";

import { searchCatalog, type CatalogItemResponse } from "../../shared/api";

interface Deps {
  readonly setStatus: (message: string) => void;
  readonly setBusy: (busy: boolean) => void;
}

export interface CatalogSearch {
  readonly query: string;
  readonly setQuery: (value: string) => void;
  readonly catalog: CatalogItemResponse[];
  readonly search: (event: FormEvent) => Promise<void>;
}

export function useCatalogSearch({ setStatus, setBusy }: Deps): CatalogSearch {
  const [query, setQuery] = useState("");
  const [catalog, setCatalog] = useState<CatalogItemResponse[]>([]);

  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus("KIS 종목 카탈로그를 검색하는 중입니다.");
    const result = await searchCatalog({ query: { q: query, limit: 20 } });
    setBusy(false);
    if (result.error) {
      setStatus("종목 검색에 실패했습니다.");
      return;
    }
    if (!Array.isArray(result.data)) {
      // A non-array 200 body means the request did not reach the API as JSON
      // (e.g. the SPA index.html served because /api is not proxied). Fail
      // clearly instead of crashing the render with `.map is not a function`.
      setCatalog([]);
      setStatus(
        "종목 검색 응답 형식이 올바르지 않습니다. API 서버(127.0.0.1:8000)가 실행 중이고 /api 프록시(개발 서버)가 동작하는지 확인하세요.",
      );
      return;
    }
    const rows = result.data;
    setCatalog(rows);
    setStatus(rows.length ? `${rows.length}개 종목을 찾았습니다.` : "검색 결과가 없습니다.");
  }

  return { query, setQuery, catalog, search };
}
