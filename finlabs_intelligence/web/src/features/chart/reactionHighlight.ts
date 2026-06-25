import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";

export interface ReactionBand {
  readonly from: Time;
  readonly to: Time;
}

const FILL = "rgba(110, 231, 183, 0.10)";
const EDGE_T0 = "rgba(110, 231, 183, 0.9)";
const EDGE_END = "rgba(110, 231, 183, 0.5)";

// Coordinates may be null when an edge falls outside the visible range; the
// renderer clamps each to the nearest pane edge so the band still reads.
interface BandCoords {
  readonly x0: number | null;
  readonly x1: number | null;
}

class ReactionPaneRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly coords: BandCoords | null) {}

  draw(): void {
    // The highlight lives behind the candles; nothing to draw in the foreground.
  }

  drawBackground(target: CanvasRenderingTarget2D): void {
    const coords = this.coords;
    if (!coords || (coords.x0 === null && coords.x1 === null)) return;
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const { width, height } = scope.mediaSize;
      const x0 = coords.x0 ?? 0;
      const x1 = coords.x1 ?? width;
      const left = Math.min(x0, x1);
      const span = Math.max(1, Math.abs(x1 - x0));

      ctx.fillStyle = FILL;
      ctx.fillRect(left, 0, span, height);

      ctx.lineWidth = 1;
      if (coords.x0 !== null) {
        ctx.strokeStyle = EDGE_T0;
        ctx.beginPath();
        ctx.moveTo(coords.x0, 0);
        ctx.lineTo(coords.x0, height);
        ctx.stroke();
      }
      if (coords.x1 !== null) {
        ctx.strokeStyle = EDGE_END;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(coords.x1, 0);
        ctx.lineTo(coords.x1, height);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }
}

class ReactionPaneView implements IPrimitivePaneView {
  private coords: BandCoords | null = null;

  constructor(private readonly source: ReactionHighlight) {}

  update(): void {
    const chart = this.source.chart;
    const band = this.source.band;
    if (!chart || !band) {
      this.coords = null;
      return;
    }
    const timeScale = chart.timeScale();
    this.coords = {
      x0: timeScale.timeToCoordinate(band.from),
      x1: timeScale.timeToCoordinate(band.to),
    };
  }

  renderer(): IPrimitivePaneRenderer {
    return new ReactionPaneRenderer(this.coords);
  }
}

// Series primitive that shades [t0, reactionEnd] behind the candles, marking the
// window the reaction label measures. Attach once and drive it with setBand.
export class ReactionHighlight implements ISeriesPrimitive<Time> {
  chart: IChartApi | null = null;
  band: ReactionBand | null = null;
  private readonly views: ReactionPaneView[];
  private requestUpdate?: () => void;

  constructor() {
    this.views = [new ReactionPaneView(this)];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.requestUpdate = undefined;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  setBand(band: ReactionBand | null): void {
    this.band = band;
    this.requestUpdate?.();
  }
}
