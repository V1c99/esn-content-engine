import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";

const client = new QueryClient({
  defaultOptions: {
    // A search for the same words gives the same answer, so there is no reason to run it
    // again when the window regains focus.
    queries: { refetchOnWindowFocus: false, staleTime: 60_000 },
  },
});

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root to mount on");
}

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
