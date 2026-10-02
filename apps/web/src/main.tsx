import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@clr/city/css/bundles/default.css";
import App from "./App";
import "./styles.css";
import "./landing.css";
import "./theme.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>,
);
