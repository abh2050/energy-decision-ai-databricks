import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { live } from "./adapters/live";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App api={live} />
  </StrictMode>,
);
