import { useCallback, useMemo, useState, type FormEvent } from "react";

import {
  createAnnotation,
  discoverNews,
  exportDataset,
  freezeDataset,
  loadChart,
  previewReaction,
  searchCatalog,
  suggestRelevance,
} from "./api/generated/sdk.gen";
import type {
  AnnotationRevisionResponse,
  CatalogItemResponse,
  ChartResponse,
  DiscoverNewsResponse,
  ExportDatasetResponse,
  FreezeDatasetResponse,
  RelevanceSuggestionResponse,
} from "./api/generated/types.gen";
import { client } from "./api/generated/client.gen";
import { CandleChart } from "./CandleChart";
import {
  formatKstTimestamp,
  kstLocalInputToIso,
  toChartCandles,
} from "./chartData";
import type { ChartSelection } from "./chartSelection";

const DEFAULT_START = "2026-06-17T09:00";
const DEFAULT_END = "2026-06-17T15:30";

client.setConfig({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? "" });

export function App() {
  const [query, setQuery] = useState("");
  const [catalog, setCatalog] = useState<CatalogItemResponse[]>([]);
  const [security, setSecurity] = useState<CatalogItemResponse | null>(null);
  const [startAt, setStartAt] = useState(DEFAULT_START);
  const [endAt, setEndAt] = useState(DEFAULT_END);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [selection, setSelection] = useState<ChartSelection | null>(null);
  const [discovery, setDiscovery] = useState<DiscoverNewsResponse | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, RelevanceSuggestionResponse>>({});
  const [annotations, setAnnotations] = useState<Record<string, AnnotationRevisionResponse>>({});
  const [actor, setActor] = useState("local-user");
  const [selectedSinks, setSelectedSinks] = useState(["db", "json", "csv"]);
  const [datasetResult, setDatasetResult] = useState<FreezeDatasetResponse | null>(null);
  const [exportResult, setExportResult] = useState<ExportDatasetResponse | null>(null);
  const [status, setStatus] = useState("종목을 검색하세요.");
  const [busy, setBusy] = useState(false);

  const chartCandles = useMemo(
    () => (chart ? toChartCandles(chart.candles) : []),
    [chart],
  );
  const handleSelection = useCallback((next: ChartSelection) => {
    setSelection(next);
  }, []);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus("KIS 종목 카탈로그를 검색하는 중입니다.");
    const result = await searchCatalog({ query: { q: query, limit: 20 } });
    setBusy(false);
    if (result.error) {
      setStatus("종목 검색에 실패했습니다.");
      return;
    }
    const rows = result.data ?? [];
    setCatalog(rows);
    setStatus(rows.length ? `${rows.length}개 종목을 찾았습니다.` : "검색 결과가 없습니다.");
  }

  async function handleLoadChart() {
    if (!security) return;
    setBusy(true);
    setSelection(null);
    setDiscovery(null);
    setSuggestions({});
    setAnnotations({});
    setStatus("Kiwoom 1분봉을 조회하는 중입니다.");
    try {
      const result = await loadChart({
        path: { symbol: security.symbol },
        query: {
          market: security.market,
          start_at: kstLocalInputToIso(startAt),
          end_at: kstLocalInputToIso(endAt),
        },
      });
      if (result.error || !result.data) {
        setStatus("차트 조회에 실패했습니다.");
        return;
      }
      setChart(result.data);
      setStatus(`${result.data.candles.length}개 1분봉을 불러왔습니다.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "차트 조회에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDiscoverNews() {
    if (!security || !selection) return;
    setBusy(true);
    setStatus("Naver 제공자 날짜별 완전 검색을 실행하는 중입니다.");
    try {
      const result = await discoverNews({
        body: {
          security_id: security.security_id,
          selected_candle_at: new Date(selection.selectedAt * 1_000).toISOString(),
        },
      });
      if (result.error || !result.data) {
        setStatus("완전한 뉴스 검색 결과를 확보하지 못했습니다.");
        return;
      }
      setDiscovery(result.data);
      const selectedOn = result.data.selected_candle_at.slice(0, 10);
      const suggestionPairs = await Promise.all(
        result.data.articles.map(async (article) => {
          const response = await suggestRelevance({
            body: {
              security_id: security.security_id,
              title: article.title,
              description: article.description,
              selected_on: selectedOn,
            },
          });
          return [article.sample_id, response.data] as const;
        }),
      );
      setSuggestions(
        Object.fromEntries(
          suggestionPairs.filter((pair) => pair[1] !== undefined),
        ) as Record<string, RelevanceSuggestionResponse>,
      );
      setStatus(`${result.data.articles.length}개 뉴스를 찾았습니다.`);
    } finally {
      setBusy(false);
    }
  }

  async function handleAnnotation(
    article: DiscoverNewsResponse["articles"][number],
    finalValue: "relevant" | "not_relevant" | "uncertain",
  ) {
    if (!security || !discovery) return;
    setBusy(true);
    try {
      const response = await createAnnotation({
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: {
          sample_id: article.sample_id,
          final_value: finalValue,
          actor,
          note: null,
        },
      });
      if (response.data) {
        setAnnotations((current) => ({
          ...current,
          [article.sample_id]: response.data!,
        }));
        setStatus(`${article.title} 라벨 리비전 ${response.data.revision}을 저장했습니다.`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleFreezeDataset() {
    if (!security || !discovery) return;
    const labeled = discovery.articles.filter((article) => annotations[article.sample_id]);
    if (!labeled.length) {
      setStatus("먼저 뉴스 한 건 이상을 라벨링하세요.");
      return;
    }
    setBusy(true);
    try {
      await Promise.all(
        labeled.map((article) => previewReaction({ body: { sample_id: article.sample_id } })),
      );
      const datasetId = `dataset-${Date.now()}`;
      const response = await freezeDataset({
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: {
          dataset_id: datasetId,
          purpose: "combined",
          cohort: "historical_publication_proxy",
          annotation_ids: labeled.map(
            (article) => annotations[article.sample_id].annotation_id,
          ),
        },
      });
      if (response.data) {
        setDatasetResult(response.data);
        const exported = await exportDataset({
          path: { dataset_id: response.data.dataset_id },
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: { sinks: selectedSinks },
        });
        setExportResult(exported.data ?? null);
        setStatus(`데이터셋 ${response.data.dataset_id}을 고정하고 내보냈습니다.`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="workspace">
      <header>
        <p className="eyebrow">FINLABS · LOCAL DATA WORKBENCH</p>
        <h1>뉴스 인텔리전스 라벨링 도구</h1>
        <p className="lede">KIS 종목 카탈로그와 Kiwoom 1분봉을 기준으로 뉴스 관측 시점을 고정합니다.</p>
      </header>

      <section className="panel search-panel" aria-labelledby="security-search">
        <div>
          <span className="step">01</span>
          <h2 id="security-search">국내 종목 선택</h2>
        </div>
        <form className="search-form" onSubmit={handleSearch}>
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
              onClick={() => {
                setSecurity(item);
                setChart(null);
                setSelection(null);
                setDiscovery(null);
                setSuggestions({});
                setAnnotations({});
                setStatus(`${item.display_name}을 선택했습니다.`);
              }}
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
      </section>

      <section className="panel chart-panel" aria-labelledby="chart-heading">
        <div className="chart-heading">
          <div>
            <span className="step">02</span>
            <h2 id="chart-heading">1분봉 관측 시점</h2>
          </div>
          <div className="range-controls">
            <label>시작 <input onChange={(event) => setStartAt(event.target.value)} type="datetime-local" value={startAt} /></label>
            <label>종료 <input onChange={(event) => setEndAt(event.target.value)} type="datetime-local" value={endAt} /></label>
            <button disabled={!security || busy} onClick={handleLoadChart} type="button">차트 불러오기</button>
          </div>
        </div>
        {chart ? (
          <CandleChart
            candles={chartCandles}
            onSelect={handleSelection}
            selectedAt={selection?.selectedAt ?? null}
          />
        ) : (
          <div className="chart-empty">종목과 조회 범위를 선택하면 Kiwoom 차트를 표시합니다.</div>
        )}
        <output aria-live="polite" className="selection" data-testid="selected-candle">
          {selection ? (
            <>
              <span>뉴스 검색 구간 · KST · 양끝 포함</span>
              <strong>{formatKstTimestamp(selection.windowStart)} — {formatKstTimestamp(selection.windowEnd)}</strong>
            </>
          ) : "캔들을 클릭하면 직전 1시간의 뉴스 검색 구간을 확정합니다."}
        </output>
        <div className="discover-action">
          <button disabled={!selection || !security || busy} onClick={handleDiscoverNews} type="button">
            선택 구간 뉴스 검색
          </button>
        </div>
      </section>

      {discovery ? (
        <section className="panel news-panel" aria-labelledby="news-heading">
          <div className="news-heading">
            <div>
              <span className="step">03</span>
              <h2 id="news-heading">검색 뉴스</h2>
            </div>
            <p>
              historical_publication_proxy / published_at_proxy · {discovery.plan_version} · 예상 API 비용 {discovery.expected_call_count}회 · 실행 {discovery.executed_call_count}회 · {discovery.complete ? "완전" : "불완전"}
            </p>
          </div>
          <label className="actor-input">
            라벨 작업자
            <input onChange={(event) => setActor(event.target.value)} value={actor} />
          </label>
          <div className="news-list">
            {discovery.articles.map((article) => (
              <article key={article.article_id}>
                <time>{article.published_at}</time>
                <h3><a href={article.canonical_url} rel="noreferrer" target="_blank">{article.title}</a></h3>
                <p>{article.description}</p>
                <small>일치 별칭 {article.matched_alias_ids.length}개</small>
                {suggestions[article.sample_id] ? (
                  <div className="suggestion">
                    자동 제안 <strong>{suggestions[article.sample_id].value}</strong> · {suggestions[article.sample_id].rule_version}
                    {suggestions[article.sample_id].evidence.map((item) => (
                      <code key={`${item.field}-${item.alias_id}`}>
                        {item.field}: “{item.matched_text}”
                      </code>
                    ))}
                  </div>
                ) : null}
                <div className="label-actions">
                  <button
                    disabled={busy || !suggestions[article.sample_id]}
                    onClick={() => handleAnnotation(
                      article,
                      suggestions[article.sample_id]?.value === "relevant"
                        ? "relevant"
                        : "uncertain",
                    )}
                    type="button"
                  >자동 제안 적용</button>
                  <button disabled={busy} onClick={() => handleAnnotation(article, "relevant")} type="button">관련</button>
                  <button disabled={busy} onClick={() => handleAnnotation(article, "not_relevant")} type="button">무관</button>
                  <button disabled={busy} onClick={() => handleAnnotation(article, "uncertain")} type="button">불확실</button>
                  {annotations[article.sample_id] ? (
                    <span>
                      최종 {annotations[article.sample_id].final_value} · rev {annotations[article.sample_id].revision}
                    </span>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          <div className="dataset-controls">
            <strong>저장 대상</strong>
            {["db", "json", "csv"].map((sink) => (
              <label key={sink}>
                <input
                  checked={selectedSinks.includes(sink)}
                  onChange={() => setSelectedSinks((current) => current.includes(sink) ? current.filter((item) => item !== sink) : [...current, sink])}
                  type="checkbox"
                /> {sink.toUpperCase()}
              </label>
            ))}
            <button disabled={busy || selectedSinks.length === 0} onClick={handleFreezeDataset} type="button">버전 스냅샷 고정</button>
            {datasetResult ? <code>{datasetResult.snapshot_checksum}</code> : null}
            {exportResult ? (
              <div className="sink-statuses">
                {exportResult.sinks.map((sink) => (
                  <span key={sink.sink}>
                    {sink.sink}: {sink.state}{sink.error_code ? ` (${sink.error_code})` : ""}
                  </span>
                ))}
                <span>제외 {datasetResult?.exclusions.length ?? 0}건 · reaction 제외: benchmark_unavailable</span>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      <p aria-live="polite" className="status">{status}</p>
    </main>
  );
}
