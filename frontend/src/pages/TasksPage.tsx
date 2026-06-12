import { useState } from "react";
import { Check, Inbox, Mail, RotateCcw, Trash2 } from "lucide-react";
import {
  useDraftAction,
  useDrafts,
  useFeatures,
  useTaskUpdate,
  useTasks,
  type TaskStatusFilter,
} from "../lib/queries";
import { EmptyState } from "../components/EmptyState";
import { formatAge } from "../lib/time";

type Tab = "tasks" | "drafts";

const PRIORITY_CLASS: Record<string, string> = {
  high: "border-danger/40 text-danger",
  urgent: "border-danger/40 text-danger",
  normal: "border-cyan-500/30 text-slate-400",
  low: "border-slate-600/40 text-slate-500",
};

function TasksTab() {
  const [filter, setFilter] = useState<TaskStatusFilter>("open");
  const { data: tasks, isLoading } = useTasks(filter);
  const update = useTaskUpdate();

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-md border border-cyan-500/20 p-0.5">
        {(["open", "done"] as const).map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setFilter(status)}
            className={`rounded px-3 py-1 font-mono text-[10px] uppercase tracking-[0.2em] transition ${
              filter === status
                ? "bg-cyan-500/15 text-accent"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Loading…</p>
      ) : (tasks ?? []).length === 0 ? (
        <EmptyState
          title={filter === "open" ? "No open tasks" : "No completed tasks"}
          hint="Inbound email tasks appear here automatically."
        />
      ) : (
        <ul className="space-y-2">
          {(tasks ?? []).map((task) => (
            <li
              key={task.id}
              className="flex flex-col items-start justify-between gap-4 rounded-lg border border-cyan-500/15 bg-panel p-4 sm:flex-row sm:items-center"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
                      PRIORITY_CLASS[task.priority] ?? PRIORITY_CLASS.normal
                    }`}
                  >
                    {task.priority}
                  </span>
                  <h3 className="text-sm font-medium text-slate-100">{task.title}</h3>
                </div>
                {task.description !== "" && (
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{task.description}</p>
                )}
                <p className="mt-1 font-mono text-[10px] text-slate-600">
                  {formatAge(task.createdAt)} ago
                </p>
              </div>
              <button
                type="button"
                disabled={update.isPending}
                onClick={() =>
                  update.mutate({ id: task.id, status: filter === "open" ? "done" : "open" })
                }
                className="mt-3 inline-flex w-full shrink-0 items-center justify-center gap-1.5 rounded-md border border-cyan-500/30 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-accent/60 hover:text-accent disabled:opacity-50 sm:mt-0 sm:w-auto"
              >
                {filter === "open" ? (
                  <>
                    <Check className="h-3.5 w-3.5" /> Mark done
                  </>
                ) : (
                  <>
                    <RotateCcw className="h-3.5 w-3.5" /> Reopen
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DraftsTab() {
  const { data: drafts, isLoading } = useDrafts();
  const action = useDraftAction();

  return (
    <div className="space-y-4">
      {isLoading ? (
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Loading…</p>
      ) : (drafts ?? []).length === 0 ? (
        <EmptyState title="No drafts awaiting review" hint="Prepared email replies show up here." />
      ) : (
        <ul className="space-y-2">
          {(drafts ?? []).map((draft) => (
            <li
              key={draft.taskId}
              className="flex flex-col items-start justify-between gap-4 rounded-lg border border-cyan-500/15 bg-panel p-4 sm:flex-row sm:items-center"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-medium text-slate-100">{draft.subject}</h3>
                  <span className="rounded border border-warning/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-warning">
                    {draft.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{draft.summary}</p>
                <p className="mt-1 font-mono text-[10px] text-slate-600">
                  {formatAge(draft.createdAt)} ago
                </p>
              </div>
              <div className="mt-3 flex w-full shrink-0 flex-col gap-2 sm:mt-0 sm:w-auto sm:flex-row">
                <button
                  type="button"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ taskId: draft.taskId, action: "approve" })}
                  className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-base shadow-glow transition hover:bg-cyan-300 disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5" /> Approve
                </button>
                <button
                  type="button"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ taskId: draft.taskId, action: "discard" })}
                  className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Discard
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function TasksPage() {
  const [tab, setTab] = useState<Tab>("tasks");
  const { data: features } = useFeatures();

  if (features && !features.mail) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <EmptyState
          title="Mail integration is disabled"
          hint="Set MAIL_ENABLED=true on the workspace and gateway deployments to activate inbox automation."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-[0.3em] text-slate-200">
        Inbox operations
      </h1>
      <div className="mt-4 flex gap-1 border-b border-cyan-500/15">
        {(
          [
            { id: "tasks", label: "Tasks", icon: Inbox },
            { id: "drafts", label: "Drafts", icon: Mail },
          ] as const
        ).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`inline-flex items-center gap-2 border-b-2 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] transition ${
              tab === id
                ? "border-accent text-accent"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
      <div className="mt-5">{tab === "tasks" ? <TasksTab /> : <DraftsTab />}</div>
    </div>
  );
}
