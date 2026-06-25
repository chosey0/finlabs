// Single entry point for the generated API: configures the client once (the
// side effect runs as soon as any feature imports a function from here) and
// re-exports the operations and response types the features use.
import { client } from "../../api/generated/client.gen";

client.setConfig({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? "" });

export { client };
export {
  createAnnotation,
  discoverNews,
  exportDataset,
  freezeDataset,
  loadChart,
  previewReaction,
  searchCatalog,
  suggestRelevance,
} from "../../api/generated/sdk.gen";
export type {
  AnnotationRevisionResponse,
  CatalogItemResponse,
  ChartResponse,
  DiscoverNewsResponse,
  ExportDatasetResponse,
  FreezeDatasetResponse,
  RelevanceSuggestionResponse,
} from "../../api/generated/types.gen";
