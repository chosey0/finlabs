// The runtime bundle (plotly.js-dist-min) ships no types of its own; it exposes
// the same surface as plotly.js, so we borrow those types. Runtime code imports
// the dist build, while `import type` for Data/Layout/etc. comes from plotly.js.
declare module "plotly.js-dist-min" {
  import * as Plotly from "plotly.js";
  export = Plotly;
}
