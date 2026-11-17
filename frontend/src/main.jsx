import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/inter"; // self-hosted: no request to a font CDN
import App from "./App";
import { followSystemTheme } from "./lib/theme";
import "./tokens.css";
import "./styles.css";

followSystemTheme();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
