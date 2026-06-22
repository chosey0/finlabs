# Chart library compatibility decision

## Decision

Use `lightweight-charts` 5.0.9 for the MVP candle selector. Keep the selection
contract independent from the rendering library so the chart can be replaced
without changing the news-window semantics.

## Evidence

- React 19 strict mode mounts and cleans up one chart instance through the effect
  lifecycle; the click callback is unsubscribed before chart removal.
- The selected Unix timestamp is preserved exactly and maps to the inclusive
  `[selected_at - 1h, selected_at]` interval in a pure tested function.
- Resize handling changes only chart width, leaving React-owned selection state
  intact.
- The fixture contains a session gap and the time scale does not synthesize
  candles for missing minutes.
- Vite production build, TypeScript `--noEmit`, and Vitest run under the pinned
  Bun version.

## Alternative

Recharts was rejected for this slice because its categorical chart primitives
require more custom work for financial time-scale behavior, crosshair clicks,
and candlestick rendering. It remains viable for aggregate analytics charts.

## Boundary

This spike proves browser bundling and the selection contract. It does not claim
pixel-perfect UX, historical chart replay, or production API integration.
