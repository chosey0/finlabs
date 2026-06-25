import type {
  AnnotationRevisionResponse,
  DiscoverNewsResponse,
  RelevanceSuggestionResponse,
} from "../../shared/api";

type Article = DiscoverNewsResponse["articles"][number];
type FinalValue = "relevant" | "not_relevant" | "uncertain";

interface ArticleCardProps {
  readonly article: Article;
  readonly suggestion: RelevanceSuggestionResponse | undefined;
  readonly annotation: AnnotationRevisionResponse | undefined;
  readonly busy: boolean;
  readonly onAnnotate: (article: Article, finalValue: FinalValue) => void;
}

export function ArticleCard({
  article,
  suggestion,
  annotation,
  busy,
  onAnnotate,
}: ArticleCardProps) {
  return (
    <article>
      <div className="article-meta">
        <time>{article.published_at}</time>
        <span className={`source-badge source-${article.source}`}>
          {article.source === "rss" ? "RSS" : "Naver"}
        </span>
      </div>
      <h3><a href={article.canonical_url} rel="noreferrer" target="_blank">{article.title}</a></h3>
      <p>{article.description}</p>
      <small>일치 별칭 {article.matched_alias_ids.length}개</small>
      {suggestion ? (
        <div className="suggestion">
          자동 제안 <strong>{suggestion.value}</strong> · {suggestion.rule_version}
          {suggestion.evidence.map((item) => (
            <code key={`${item.field}-${item.alias_id}`}>
              {item.field}: “{item.matched_text}”
            </code>
          ))}
        </div>
      ) : null}
      <div className="label-actions">
        <button
          className="label-suggest"
          disabled={busy || !suggestion}
          onClick={() => onAnnotate(
            article,
            suggestion?.value === "relevant" ? "relevant" : "uncertain",
          )}
          type="button"
        >자동 제안 적용</button>
        <button className="label-relevant" disabled={busy} onClick={() => onAnnotate(article, "relevant")} type="button">관련</button>
        <button className="label-not-relevant" disabled={busy} onClick={() => onAnnotate(article, "not_relevant")} type="button">무관</button>
        <button className="label-uncertain" disabled={busy} onClick={() => onAnnotate(article, "uncertain")} type="button">불확실</button>
        {annotation ? (
          <span className={`label-final label-final-${annotation.final_value}`}>
            최종 {annotation.final_value} · rev {annotation.revision}
          </span>
        ) : null}
      </div>
    </article>
  );
}
