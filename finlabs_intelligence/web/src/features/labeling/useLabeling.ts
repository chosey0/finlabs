import { useCallback, useState } from "react";

import {
  createAnnotation,
  discoverNews as discoverNewsApi,
  exportDataset,
  freezeDataset,
  previewReaction,
  suggestRelevance,
  type AnnotationRevisionResponse,
  type CatalogItemResponse,
  type DiscoverNewsResponse,
  type ExportDatasetResponse,
  type FreezeDatasetResponse,
  type RelevanceSuggestionResponse,
} from "../../shared/api";
import type { ChartSelection } from "../chart/chartSelection";

type Article = DiscoverNewsResponse["articles"][number];
type FinalValue = "relevant" | "not_relevant" | "uncertain";

interface Deps {
  readonly security: CatalogItemResponse | null;
  readonly setStatus: (message: string) => void;
  readonly setBusy: (busy: boolean) => void;
}

export interface Labeling {
  readonly discovery: DiscoverNewsResponse | null;
  readonly suggestions: Record<string, RelevanceSuggestionResponse>;
  readonly annotations: Record<string, AnnotationRevisionResponse>;
  readonly selectedSinks: string[];
  readonly setSelectedSinks: (updater: (current: string[]) => string[]) => void;
  readonly datasetResult: FreezeDatasetResponse | null;
  readonly exportResult: ExportDatasetResponse | null;
  readonly newsExpanded: boolean;
  readonly setNewsExpanded: (updater: (current: boolean) => boolean) => void;
  readonly discoverNews: (selection: ChartSelection | null) => Promise<void>;
  readonly annotate: (article: Article, finalValue: FinalValue) => Promise<void>;
  readonly freeze: () => Promise<void>;
  readonly reset: () => void;
}

export function useLabeling({ security, setStatus, setBusy }: Deps): Labeling {
  const [discovery, setDiscovery] = useState<DiscoverNewsResponse | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, RelevanceSuggestionResponse>>({});
  const [annotations, setAnnotations] = useState<Record<string, AnnotationRevisionResponse>>({});
  const [actor] = useState("local-user");
  const [selectedSinks, setSelectedSinks] = useState(["db", "json", "csv"]);
  const [datasetResult, setDatasetResult] = useState<FreezeDatasetResponse | null>(null);
  const [exportResult, setExportResult] = useState<ExportDatasetResponse | null>(null);
  const [newsExpanded, setNewsExpanded] = useState(true);

  const reset = useCallback(() => {
    setDiscovery(null);
    setSuggestions({});
    setAnnotations({});
  }, []);

  async function discoverNews(selection: ChartSelection | null) {
    if (!security || !selection) return;
    setBusy(true);
    setStatus("Naver 제공자 날짜별 완전 검색을 실행하는 중입니다.");
    try {
      const result = await discoverNewsApi({
        body: {
          security_id: security.security_id,
          selected_candle_at: new Date(selection.selectedAt * 1_000).toISOString(),
        },
      });
      if (result.error || !result.data) {
        // Surface the real cause: 409 = Naver pagination/completeness, 502 =
        // provider/auth error, 422 = validation. Without the backend's safe
        // message every failure looks identical.
        const detail = result.error as
          | { message?: string; code?: string }
          | undefined;
        const status = result.response?.status;
        setStatus(
          detail?.message
            ? `뉴스 검색 실패${status ? ` [${status}]` : ""}: ${detail.message}${detail.code ? ` (${detail.code})` : ""}`
            : "완전한 뉴스 검색 결과를 확보하지 못했습니다.",
        );
        return;
      }
      setDiscovery(result.data);
      setNewsExpanded(() => true);
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

  async function annotate(article: Article, finalValue: FinalValue) {
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

  async function freeze() {
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

  return {
    discovery,
    suggestions,
    annotations,
    selectedSinks,
    setSelectedSinks,
    datasetResult,
    exportResult,
    newsExpanded,
    setNewsExpanded,
    discoverNews,
    annotate,
    freeze,
    reset,
  };
}
