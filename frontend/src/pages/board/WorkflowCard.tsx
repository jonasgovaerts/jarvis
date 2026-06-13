import { motion } from "framer-motion";
import { useNavigate } from "react-router";
import { CircleDot, Clock, GitPullRequest, MessagesSquare, Trash2 } from "lucide-react";
import type { BoardItem } from "@jarvis/events";
import { formatAge } from "../../lib/time";
import { useDeleteWorkflow } from "../../lib/queries";

const VERDICT_CLASS: Record<string, string> = {
  CodeChange: "border-accent/40 text-accent",
  Misconfiguration: "border-warning/40 text-warning",
  NotActionable: "border-slate-500/40 text-slate-400",
};

interface WorkflowCardProps {
  item: BoardItem;
  attention?: boolean;
}

export function WorkflowCard({ item, attention = false }: WorkflowCardProps) {
  const navigate = useNavigate();
  const deleteWorkflow = useDeleteWorkflow();
  const isIssue = item.sourceType === "Issue";

  return (
    <motion.div
      layout
      layoutId={item.name}
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/workflows/${encodeURIComponent(item.name)}`)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          navigate(`/workflows/${encodeURIComponent(item.name)}`);
        }
      }}
      className={`group cursor-pointer rounded-md border bg-panel p-3 text-left transition focus:outline-none focus-visible:border-accent/60 ${
        attention
          ? "border-danger/40 ring-1 ring-danger/50 hover:shadow-[0_0_12px_-2px_rgb(244_63_94/0.35)]"
          : "border-cyan-500/15 hover:border-accent/40 hover:shadow-glow"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="line-clamp-2 text-sm font-medium text-slate-100">{item.title}</p>
        <div className="flex shrink-0 items-center">
          {item.prUrl !== "" && (
            <a
              href={item.prUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              title="Open pull request"
              className="rounded p-0.5 text-slate-500 transition hover:text-accent"
            >
              <GitPullRequest className="h-3.5 w-3.5" />
            </a>
          )}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              deleteWorkflow.mutate(item.name);
            }}
            className="rounded p-0.5 text-slate-500 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
            title="Delete workflow"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-cyan-500/20 bg-cyan-500/5 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-slate-400">
          {item.repository}
        </span>
        <span className="inline-flex items-center gap-1 rounded border border-secondary/30 bg-secondary/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-secondary">
          {isIssue ? (
            <CircleDot className="h-2.5 w-2.5" />
          ) : (
            <MessagesSquare className="h-2.5 w-2.5" />
          )}
          {isIssue ? "Issue" : "Chat"}
        </span>
        {item.verdict !== null && (
          <span
            className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
              VERDICT_CLASS[item.verdict] ?? "border-slate-500/40 text-slate-400"
            }`}
          >
            {item.verdict}
          </span>
        )}
      </div>

      {item.message !== "" && (
        <p className="mt-2 truncate text-xs text-slate-500" title={item.message}>
          {item.message}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="font-mono text-[9px] uppercase tracking-wider text-slate-600">
          {item.name}
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-[10px] text-slate-500">
          <Clock className="h-3 w-3" />
          {formatAge(item.updatedAt ?? item.createdAt)}
        </span>
      </div>
    </motion.div>
  );
}
