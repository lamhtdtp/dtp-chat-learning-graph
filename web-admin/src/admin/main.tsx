import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource/be-vietnam-pro/vietnamese-400.css";
import "@fontsource/be-vietnam-pro/vietnamese-500.css";
import "@fontsource/be-vietnam-pro/vietnamese-600.css";
import "@fontsource/be-vietnam-pro/vietnamese-700.css";
import "@fontsource/baloo-2/vietnamese-600.css";
import "@fontsource/baloo-2/vietnamese-700.css";
import "katex/dist/katex.min.css";   // render công thức $…$ trong ô soạn + xem trước
import "../styles.css";       // token màu + nút + modal dùng chung
import "./admin.css";         // layout dashboard riêng
import { AdminApp } from "./AdminApp";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AdminApp />
  </React.StrictMode>,
);
