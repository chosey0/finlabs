# Phase 0 feasibility decision

## Status

The implementation may proceed to the shared-contract foundation. Production
consumer slices remain gated by their own tests and by an eventual credentialed
Kiwoom smoke test outside CI.

## Evidence register

| Gate | Decision and evidence |
|---|---|
| Chart selection | `lightweight-charts` 5.0.9 bundles with Vite, runs under React strict-mode lifecycle cleanup, and preserves the exact clicked Unix timestamp through the tested pure selection contract. |
| Kiwoom timestamp | `ka10080` naive `cntr_tm` is interpreted explicitly as `Asia/Seoul`; normalization rejects malformed, conflicting, identity-mixed, and out-of-range rows and emits ordered/deduplicated canonical candles. |
| Catalog and aliases | A catalog snapshot carries acquisition time/checksum/version; aliases carry source, validity range, and `current_only` versus `validity_ranged` historical-name status. Discovery freezes alias and snapshot identifiers. |
| Benchmark | Kiwoom's REST guide exposes the domestic chart/industry surfaces. The implemented `ka20005` path uses `POST /api/dostk/chart`, `inds_cd`, `tic_scope`, optional `base_dt`, and `inds_min_pole_qry`; KOSPI `001` and KOSDAQ `101` are the only approved ownership mappings. Mocked SDK/adapter tests verify aware aligned fixtures, source identity, and checksum provenance. A credentialed smoke test remains an operational release check. |
| Naver query plan | `naver-discovery-plan-v1` deterministically emits the complete alias × provider-date matrix for supported RFC-822 offsets `[-12:00,+14:00]`, including adjacent dates for KST windows. |
| OpenAPI/client | The repo will commit the FastAPI OpenAPI artifact and exact-pinned generated TypeScript client in Phase 1. The foundation gate requires a zero-diff regeneration command before consumer routes can merge. |

## Source boundary

- Primary: Kiwoom REST API guide, domestic `업종` and `차트` categories:
  <https://openapi.kiwoom.com/guide/apiguide>
- Exact `ka20005` field names were cross-checked against a public extraction of
  Kiwoom's 526-page REST specification and an independently generated typed
  client. They are fixture evidence, not a substitute for credentialed live
  verification.

Production runtime wires the Kiwoom stock-minute and approved industry-minute
adapter into reaction preview. It never substitutes the selected stock, zero,
or a different index for an unavailable benchmark; missing or incomplete proof
still produces a typed exclusion and a NULL reaction target.
