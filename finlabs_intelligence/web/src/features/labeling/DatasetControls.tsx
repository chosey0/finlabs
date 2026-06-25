import type { ExportDatasetResponse, FreezeDatasetResponse } from "../../shared/api";

interface DatasetControlsProps {
  readonly selectedSinks: string[];
  readonly setSelectedSinks: (updater: (current: string[]) => string[]) => void;
  readonly busy: boolean;
  readonly onFreeze: () => void;
  readonly datasetResult: FreezeDatasetResponse | null;
  readonly exportResult: ExportDatasetResponse | null;
}

export function DatasetControls({
  selectedSinks,
  setSelectedSinks,
  busy,
  onFreeze,
  datasetResult,
  exportResult,
}: DatasetControlsProps) {
  return (
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
      <button disabled={busy || selectedSinks.length === 0} onClick={onFreeze} type="button">버전 스냅샷 고정</button>
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
  );
}
