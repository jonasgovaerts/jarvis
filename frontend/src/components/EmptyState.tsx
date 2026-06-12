import { Scan } from "lucide-react";

interface EmptyStateProps {
  title: string;
  hint?: string;
  compact?: boolean;
}

/** HUD-style placeholder for empty lists. */
export function EmptyState({ title, hint, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-cyan-500/20 text-center ${
        compact ? "px-3 py-6" : "px-6 py-12"
      }`}
    >
      <Scan className={`text-cyan-500/40 ${compact ? "h-4 w-4" : "h-6 w-6"}`} />
      <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500">{title}</p>
      {hint !== undefined && <p className="text-xs text-slate-600">{hint}</p>}
    </div>
  );
}
