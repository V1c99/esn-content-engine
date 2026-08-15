import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "./api/client";
import { InterpretationBar } from "./components/Interpretation";
import { ResultCard } from "./components/ResultCard";

const EXAMPLES = [
  "volunteers hiking in the mountains",
  "people laughing at night",
  "happy volunteers for recruitment, no booze",
  "clips of the basketball game",
];

function queryInUrl(): string {
  return new URLSearchParams(window.location.search).get("q") ?? "";
}

export function App() {
  const [text, setText] = useState(queryInUrl);
  // Only updated on submit, so the app does not search on every keystroke.
  const [submitted, setSubmitted] = useState(queryInUrl);

  const search = useQuery({
    queryKey: ["search", submitted],
    enabled: submitted !== "",
    queryFn: async () => {
      const { data, error } = await api.POST("/search", { body: { q: submitted } });
      if (error !== undefined) {
        throw new Error("the search failed");
      }
      return data;
    },
  });

  // The query goes in the address bar so a search can be sent to somebody as a link.
  function run(value: string) {
    setText(value);
    setSubmitted(value);
    const path = window.location.pathname;
    window.history.replaceState(null, "", value === "" ? path : `${path}?q=${encodeURIComponent(value)}`);
  }

  const best = search.data?.hits[0]?.rrf_score ?? 0;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">ESN Content Engine</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-500">
          Semantic, keyword and tag search over the ESN Bucharest media library, fused by rank
          in one SQL query. Saying &ldquo;no booze&rdquo; in the query excludes the drinks and
          the bars they were shot in.
        </p>
      </header>

      <form
        className="mt-6 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          run(text.trim());
        }}
      >
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="what are you looking for?"
          className="flex-1 rounded-lg border border-slate-300 px-4 py-2 outline-none focus:border-slate-500"
        />
        <button
          type="submit"
          className="rounded-lg bg-slate-900 px-5 py-2 font-medium text-white hover:bg-slate-700"
        >
          Search
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => run(example)}
            className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-slate-400"
          >
            {example}
          </button>
        ))}
      </div>

      {search.isFetching && <p className="mt-8 text-slate-400">Searching...</p>}
      {search.isError && <p className="mt-8 text-rose-700">The search failed.</p>}

      {search.data !== undefined && !search.isFetching && (
        <section className="mt-8">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <InterpretationBar value={search.data.interpretation} />
            <span className="text-sm text-slate-400">
              {search.data.hits.length} results in {search.data.took_ms} ms
            </span>
          </div>

          {search.data.hits.length === 0 ? (
            <p className="mt-8 text-slate-500">Nothing matched.</p>
          ) : (
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {search.data.hits.map((hit) => (
                <ResultCard key={`${hit.media.id}-${hit.timestamp_s}`} hit={hit} best={best} />
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
