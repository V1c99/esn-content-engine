import type { Interpretation as Understood } from "../api/client";

/** Shows what the engine understood. If it read the query wrong, the results look random. */
export function InterpretationBar({ value }: { value: Understood }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Chip label="searched for" value={value.searched_for} tone="neutral" />
      {value.kind !== null && <Chip label="only" value={value.kind} tone="neutral" />}

      {/* The safety floor has its own badge below, so it is not repeated here. */}
      {value.applied_rules
        .filter((rule) => rule !== "safety-floor")
        .map((rule) => (
          <Chip key={rule} label="excluding" value={rule} tone="blocked" />
        ))}

      {value.safety_floor && (
        <span
          className="rounded-full bg-amber-100 px-3 py-1 font-medium text-amber-900"
          title="Anything flagged reputational or unusable is dropped whenever a query excludes something"
        >
          safety floor on
        </span>
      )}

      {value.dropped_words.length > 0 && (
        <span className="text-slate-400">dropped: {value.dropped_words.join(", ")}</span>
      )}
    </div>
  );
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "blocked";
}) {
  const colours =
    tone === "blocked" ? "bg-rose-100 text-rose-900" : "bg-slate-200 text-slate-800";
  return (
    <span className={`rounded-full px-3 py-1 ${colours}`}>
      <span className="opacity-60">{label} </span>
      <span className="font-medium">{value}</span>
    </span>
  );
}
