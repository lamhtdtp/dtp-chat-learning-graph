import React from "react";
import ReactDOM from "react-dom/client";
// Self-host font (CSP chặt — KHÔNG CDN): @fontsource nhúng woff2 qua bundler.
// Be Vietnam Pro (thân + UI) 400–800, Baloo 2 (điểm nhấn) 500–700; kèm subset
// tiếng Việt để dấu hiển thị đúng.
import "@fontsource/be-vietnam-pro/vietnamese-400.css";
import "@fontsource/be-vietnam-pro/vietnamese-500.css";
import "@fontsource/be-vietnam-pro/vietnamese-600.css";
import "@fontsource/be-vietnam-pro/vietnamese-700.css";
import "@fontsource/be-vietnam-pro/vietnamese-800.css";
import "@fontsource/be-vietnam-pro/latin-400.css";
import "@fontsource/be-vietnam-pro/latin-600.css";
import "@fontsource/baloo-2/vietnamese-500.css";
import "@fontsource/baloo-2/vietnamese-600.css";
import "@fontsource/baloo-2/vietnamese-700.css";
import "@fontsource/baloo-2/latin-700.css";
import "katex/dist/katex.min.css";
import "./styles.css";
import "./learn/learn.css";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
