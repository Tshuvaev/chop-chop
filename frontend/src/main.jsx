import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import Faq from "./Faq";
import "./index.css";

function resolvePage() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/faq") {
    return <Faq />;
  }
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {resolvePage()}
  </React.StrictMode>
);
