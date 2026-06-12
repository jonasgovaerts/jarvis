import { useMemo } from "react";
import { Outlet } from "react-router";
import { Activity } from "lucide-react";
import { useDrafts, useTasks, useWorkflows } from "../../lib/queries";
import { EmptyState } from "../../components/EmptyState";
import { BoardColumn } from "./BoardColumn";
import { NeedsAttentionStrip } from "./NeedsAttentionStrip";
import { COLUMNS, groupItems } from "./columns";

export function BoardPage() {
  const { data: items, isLoading } = useWorkflows();
  const { data: openTasks } = useTasks("open");
  const { data: drafts } = useDrafts();

  const grouped = useMemo(() => groupItems(items ?? []), [items]);
  const pendingDraftCount = useMemo(
    () => (drafts ?? []).filter((draft) => draft.status === "pending").length,
    [drafts],
  );
  const activeCount = (items ?? []).length;

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="inline-flex items-center gap-2 font-mono text-sm font-semibold uppercase tracking-[0.3em] text-slate-200">
            <Activity className="h-4 w-4 text-accent" />
            Operations board
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            {isLoading
              ? "Scanning work items…"
              : `${activeCount} work item${activeCount === 1 ? "" : "s"} tracked`}
          </p>
        </div>
      </header>

      <NeedsAttentionStrip
        items={grouped.needsAttention}
        openTaskCount={openTasks?.length ?? 0}
        pendingDraftCount={pendingDraftCount}
      />

      {!isLoading && activeCount === 0 ? (
        <EmptyState
          title="No active operations"
          hint="Connected repositories are quiet. New work items appear here in real time."
        />
      ) : (
        <div className="grid grid-cols-1 md:flex min-h-0 flex-1 gap-3 md:overflow-x-auto pb-2">
          {COLUMNS.map((column) => (
            <BoardColumn key={column} title={column} items={grouped.byColumn.get(column) ?? []} />
          ))}
        </div>
      )}

      <Outlet />
    </div>
  );
}
