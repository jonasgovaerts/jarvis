import { Link } from "react-router";
import { AlertTriangle, Inbox, MailWarning } from "lucide-react";
import type { BoardItem } from "@jarvis/events";
import { WorkflowCard } from "./WorkflowCard";

interface NeedsAttentionStripProps {
  items: BoardItem[];
  openTaskCount: number;
  pendingDraftCount: number;
}

export function NeedsAttentionStrip({
  items,
  openTaskCount,
  pendingDraftCount,
}: NeedsAttentionStripProps) {
  if (items.length === 0 && openTaskCount === 0 && pendingDraftCount === 0) {
    return null;
  }

  return (
    <section className="rounded-lg border border-danger/30 bg-danger/5 p-3 ring-1 ring-danger/20">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="inline-flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-danger">
          <AlertTriangle className="h-3.5 w-3.5" />
          Needs attention
        </h2>
        {openTaskCount > 0 && (
          <Link
            to="/tasks"
            className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning transition hover:bg-warning/20"
          >
            <Inbox className="h-3 w-3" />
            {openTaskCount} open task{openTaskCount === 1 ? "" : "s"}
          </Link>
        )}
        {pendingDraftCount > 0 && (
          <Link
            to="/tasks"
            className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning transition hover:bg-warning/20"
          >
            <MailWarning className="h-3 w-3" />
            {pendingDraftCount} draft{pendingDraftCount === 1 ? "" : "s"} pending
          </Link>
        )}
      </div>
      {items.length > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => (
            <WorkflowCard key={item.name} item={item} attention />
          ))}
        </div>
      )}
    </section>
  );
}
