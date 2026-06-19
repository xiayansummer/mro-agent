import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary
      fallback={
        <div style={{ padding: 24, textAlign: "center", color: "#64748b", fontSize: 14, lineHeight: 1.8 }}>
          页面发生错误,请刷新重试。
          <br />
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: 12, padding: "6px 16px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer" }}
          >
            刷新页面
          </button>
        </div>
      }
    >
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
