import type { Hit } from "../api/client";

/** One result. The media files are not in the repository, so this shows what is known. */
export function ResultCard({ hit, best }: { hit: Hit; best: number }) {
  const media = hit.media;
  const share = best > 0 ? hit.rrf_score / best : 0;

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="truncate font-mono text-sm text-slate-900" title={media.name}>
          {media.name}
        </h3>
        <span
          className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
            media.kind === "video" ? "bg-violet-100 text-violet-800" : "bg-sky-100 text-sky-800"
          }`}
        >
          {media.kind}
        </span>
      </div>

      <p className="mt-1 truncate text-sm text-slate-500" title={media.event ?? ""}>
        {media.event ?? "no event"}
      </p>

      {media.place !== null && (
        <p className="mt-2 truncate text-xs text-slate-400" title={media.place}>
          {media.place}
        </p>
      )}

      <div className="mt-3 flex items-center gap-2">
        {/* How strong this hit is next to the best one on the page. */}
        <div className="h-1.5 flex-1 rounded-full bg-slate-100">
          <div
            className="h-1.5 rounded-full bg-emerald-500"
            style={{ width: `${Math.round(share * 100)}%` }}
          />
        </div>
        <span className="font-mono text-xs text-slate-400">{hit.rrf_score.toFixed(4)}</span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs">
        {hit.timestamp_s > 0 && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">
            at {Math.round(hit.timestamp_s)}s
          </span>
        )}
        {media.alcohol_visible && (
          <span className="rounded bg-rose-100 px-2 py-0.5 text-rose-800">alcohol</span>
        )}
      </div>
    </article>
  );
}
