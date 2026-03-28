import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./app.css";

const rootElement = document.getElementById("react-dashboard-root");

if (rootElement instanceof HTMLDivElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App rootElement={rootElement} />
    </React.StrictMode>,
  );
}
