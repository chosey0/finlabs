import { ArticleCard } from "./ArticleCard";
import { DatasetControls } from "./DatasetControls";
import type { Labeling } from "./useLabeling";

interface NewsPanelProps {
  readonly labeling: Labeling;
  readonly busy: boolean;
}

export function NewsPanel({ labeling, busy }: NewsPanelProps) {
  const {
    discovery,
    suggestions,
    annotations,
    selectedSinks,
    setSelectedSinks,
    datasetResult,
    exportResult,
    newsExpanded,
    setNewsExpanded,
  } = labeling;
  return (
    <section className="panel news-panel" aria-labelledby="news-heading">
      <div className="news-heading">
        <div>
          <span className="step">03</span>
          <h2 id="news-heading">
            <button
              aria-controls="news-accordion-content"
              aria-expanded={newsExpanded}
              className="accordion-toggle"
              onClick={() => setNewsExpanded((current) => !current)}
              type="button"
            >
              검색 뉴스
              <span aria-hidden="true" className="accordion-icon">{newsExpanded ? "−" : "+"}</span>
            </button>
          </h2>
        </div>
        <p>
          {discovery
            ? `historical_publication_proxy / published_at_proxy · ${discovery.plan_version} · 예상 API 비용 ${discovery.expected_call_count}회 · 실행 ${discovery.executed_call_count}회 · ${discovery.complete ? "완전" : "불완전"}`
            : "선택한 차트 구간의 뉴스가 여기에 표시됩니다."}
        </p>
      </div>
      <div className="accordion-content news-accordion-content" hidden={!newsExpanded} id="news-accordion-content">
      {discovery ? (
        <>
      {/* <label className="actor-input">
        라벨 작업자
        <input onChange={(event) => setActor(event.target.value)} value={actor} />
      </label> */}
      <div className="news-list">
        {discovery.articles.map((article) => (
          <ArticleCard
            key={article.article_id}
            article={article}
            suggestion={suggestions[article.sample_id]}
            annotation={annotations[article.sample_id]}
            busy={busy}
            onAnnotate={labeling.annotate}
          />
        ))}
      </div>
      <DatasetControls
        selectedSinks={selectedSinks}
        setSelectedSinks={setSelectedSinks}
        busy={busy}
        onFreeze={labeling.freeze}
        datasetResult={datasetResult}
        exportResult={exportResult}
      />
        </>
      ) : (
        <div className="news-empty">캔들을 선택한 뒤 뉴스 검색을 실행하세요.</div>
      )}
      </div>
    </section>
  );
}
