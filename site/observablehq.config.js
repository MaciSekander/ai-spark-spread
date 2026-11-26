// Observable Framework config: https://observablehq.com/framework/config
export default {
  title: "The AI Spark Spread",
  root: "src",
  pages: [
    {name: "Today's spread", path: "/"},
    {name: "Methods & sources", path: "/methods"}
  ],
  sidebar: false,
  toc: false,
  pager: false,
  style: "style.css",   // imports the light/dark theme, then adds site styles
  head: `<meta name="description" content="Who captures the money in one GPU hour: power, the GPU owner, or the token seller? Updated daily.">`,
  header: `<nav class="site-nav"><a href="./">Today's spread</a><a href="./methods">Methods &amp; sources</a></nav>`,
  footer: `Data: U.S. EIA, Vast.ai, OpenRouter, SemiAnalysis InferenceX. Rental and token prices are public asking prices, not settled trades. Rebuilt daily.`
};
