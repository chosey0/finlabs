# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-06-23
- Primary product surfaces: `finlabs_intelligence/web` labeling workbench. This document currently governs that surface; other FinLabs UI surfaces need an explicit refresh before using it as their contract.
- Evidence reviewed: `finlabs_intelligence/web/src/App.tsx`, `src/styles.css`, `src/CandleChart.tsx`, `e2e/labeling-workflow.e2e.ts`, `package.json`, and `finlabs_intelligence/README.md`.

## Brand
- Personality: technical, precise, calm, and optimized for sustained analysis work.
- Trust signals: visible provenance, explicit time ranges, stable identifiers, operation status, and clear disabled states.
- Avoid: decorative finance imagery, consumer-trading aesthetics, hidden data lineage, and attention-seeking motion.

## Product goals
- Goals: help an analyst select a domestic security, fix a chart observation time, review discovered news, label it, and freeze a reproducible dataset.
- Non-goals: trading/order entry, portfolio monitoring, news consumption, or strategy/backtest UI.
- Success signals: the active security and workflow step remain obvious; analysts can complete the labeling flow without losing provenance or temporal context.

## Personas and jobs
- Primary personas: internal data annotators and market-data researchers.
- User jobs: find a security quickly, inspect its chart, choose a candle, judge article relevance, and preserve a versioned output.
- Key contexts of use: desktop-first local workbench, long sessions, dense Korean-language market metadata.

## Information architecture
- Primary navigation: workflow order rather than application-wide navigation.
- Core routes/screens: one labeling workspace containing security selection, chart observation, news labeling, and dataset export.
- Content hierarchy: compact product context appears in the top header, global operation status remains visible between the header and workspace, persistent security context stays on the left, chart observation precedes news labeling in the main column, and provenance sits next to the data it qualifies.

## Design principles
- Keep context persistent: security selection stays visible beside downstream analysis on desktop.
- Make workflow state explicit: retain numbered stages, selected states, status text, and disabled actions.
- Prefer density with readability: compact controls and metadata must not compete with chart and article content.
- Tradeoffs: desktop analysis efficiency takes priority; narrow screens fall back to a single column instead of preserving a cramped sidebar.

## Visual language
- Color: near-black navy surfaces, slate borders/text, emerald for active and primary states.
- Typography: system sans with Korean fallbacks; strong hierarchy and tabular/metadata-friendly sizing.
- Spacing/layout rhythm: 8–10px control gaps, 18–24px panel padding, 18–20px major gaps.
- Shape/radius/elevation: restrained 8–18px radii, thin borders, one low-contrast panel shadow.
- Motion: none required; transitions must be short and functional if introduced.
- Imagery/iconography: text-first; use icons only when they reduce reading effort.

## Components
- Existing components to reuse: `CandleChart`, accordion panel, stage heading, range controls, chart action group, security result, status output, news card, label actions.
- New/changed components: domestic-security selection becomes a left sidebar at desktop widths and a bounded top panel on smaller screens; chart loading and selected-window news discovery remain adjacent actions; the chart toggle hides only the visualization while keeping query controls and selection context visible; the news section collapses its content while preserving state.
- Variants and states: expanded, collapsed, hover, selected, disabled, loading/busy, empty, stale provenance, and error status.
- Token/component ownership: Tailwind CSS v4 is the styling engine; shared semantic styles remain in `src/styles.css` until component extraction is justified.

## Accessibility
- Target standard: WCAG 2.1 AA for the local workbench.
- Keyboard/focus behavior: all form controls and result buttons remain keyboard reachable with visible browser focus; accordion headings are buttons with `aria-expanded` and `aria-controls`.
- Contrast/readability: muted metadata remains secondary but readable against dark surfaces; active emerald is never the sole label for state.
- Screen-reader semantics: use landmark elements, associated headings, labels, contextual `output`, and one atomic global `role="status"` live region outside scrolling result content.
- Reduced motion and sensory considerations: no required animation or color-only critical status.

## Responsive behavior
- Supported breakpoints/devices: modern desktop browsers first; usable down to 320px.
- Layout adaptations: sidebar/workspace begins at Tailwind `lg`; chart and news remain a single vertical sequence in the work area; the page remains fixed to `100dvh` while result regions scroll internally.
- Touch/hover differences: controls keep practical touch targets; essential information cannot depend on hover.

## Interaction states
- Loading: disable conflicting actions and explain the active operation in the live status.
- Empty: state the next action for catalog, chart, and news content.
- Initial chart range: use the current KST date with the regular-session defaults `09:00–15:30`.
- Error: show a safe, actionable cause in the status region.
- Success: preserve the selected item and report counts/version identifiers.
- Disabled: retain legibility while clearly reducing emphasis.
- Offline/slow network: retain current inputs and context; status text communicates pending or failed requests.

## Content voice
- Tone: concise, factual Korean with domain terms shown consistently.
- Terminology: use 종목, 관측 시점, 검색 구간, 라벨, 리비전, 데이터셋, and provenance/version names from API contracts.
- Microcopy rules: lead with the object/action; state counts and failure causes; do not imply canonical time semantics for proxy cohorts.

## Implementation constraints
- Framework/styling system: React 19, Vite 7, Tailwind CSS v4 through `@tailwindcss/vite`.
- Design-token constraints: extend the existing navy/slate/emerald palette before adding colors or a new token layer.
- Performance constraints: no runtime styling library; keep chart width responsive, prevent document-level scrolling, and avoid sidebar reflow during result updates.
- Compatibility constraints: local Vite development and the current Playwright/Chrome workflow.
- Test/screenshot expectations: run typecheck/build and the existing labeling E2E when backend fixtures are available; visually check desktop and narrow viewport layout after structural changes.

## Open questions
- [ ] Decide whether sidebar selection should persist across sessions / product owner / affects local state design.
- [ ] Confirm whether other FinLabs UI surfaces should adopt this visual language / product owner / affects document scope.
