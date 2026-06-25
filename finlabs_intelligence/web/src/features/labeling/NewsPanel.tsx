import { ArticleCard } from "./ArticleCard";
import type { Labeling } from "./useLabeling";

interface NewsPanelProps {
  readonly labeling: Labeling;
  readonly busy: boolean;
}

export function NewsPanel({ labeling, busy }: NewsPanelProps) {
  const { discovery, suggestions, annotations } = labeling;
  return (
    <section className="pane news-pane" aria-label="뉴스">
      <header className="pane-head">
        <h2>뉴스{discovery ? ` · ${discovery.articles.length}` : ""}</h2>
        <p className="pane-meta">
          {discovery
            ? `${discovery.plan_version} · API ${discovery.executed_call_count}/${discovery.expected_call_count}회 · ${discovery.complete ? "완전" : "불완전"}`
            : "선택 구간의 뉴스가 여기에 표시됩니다."}
        </p>
      </header>
      <div className="pane-body">
        {discovery ? (
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
        ) : (
          <div className="news-empty">캔들을 선택한 뒤 뉴스 검색을 실행하세요.</div>
        )}
      </div>
    </section>
  );
}
