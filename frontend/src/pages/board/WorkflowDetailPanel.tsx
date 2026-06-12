import { useNavigate, useParams } from "react-router";
import { motion } from "framer-motion";
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  GitPullRequest,
  RotateCcw,
  X,
} from "lucide-react";
import type { WorkflowEvent } from "@jarvis/events";
import { useWorkflowAction, useWorkflowDetail, type WorkflowAction } from "../../lib/queries";
import { formatTimestamp } from "../../lib/time";

function eventMessage(event: WorkflowEvent): string {
  const message: unknown = event.data?.message;
  return typeof message === "string" ? message : "";
}

function shortSubject(subject: string): string {
  return subject.replace(/^jarvis\./, "");
}

function JsonSection({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="group rounded-md border border-cyan-500/15 bg-base/60">
      <summary className="flex cursor-pointer items-center justify-between px-3 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 select-none">
        {label}
        <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <pre className="max-h-72 overflow-auto border-t border-cyan-500/10 p-3 font-mono text-[11px] leading-relaxed text-slate-400">
        {JSON.stringify(value ?? null, null, 2)}
      </pre>
    </details>
  );
}

export function WorkflowDetailPanel() {
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useWorkflowDetail(name);
  const action = useWorkflowAction(name);

  const close = () => navigate("/");
  const run = (kind: WorkflowAction) => action.mutate(kind);

  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-base/60 backdrop-blur-[2px]"
        onClick={close}
        aria-hidden
      />
      <motion.aside
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        transition={{ type: "tween", duration: 0.22, ease: "easeOut" }}
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[540px] flex-col border-l border-cyan-500/20 bg-panel shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-cyan-500/15 p-5">
          <div className="min-w-0">
            <p className="truncate font-mono text-xs uppercase tracking-[0.2em] text-accent">
              {name}
            </p>
            {data !== undefined && (
              <h2 className="mt-1 text-base font-semibold text-slate-100">{data.item.title}</h2>
            )}
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close panel"
            className="rounded p-1 text-slate-500 transition hover:bg-cyan-500/10 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {isLoading && (
            <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Retrieving telemetry…
            </p>
          )}
          {isError && (
            <p className="font-mono text-xs uppercase tracking-[0.25em] text-danger">
              Failed to load workflow
            </p>
          )}

          {data !== undefined && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                    data.item.phase === "Failed"
                      ? "border-danger/40 bg-danger/10 text-danger"
                      : "border-accent/40 bg-cyan-500/10 text-accent"
                  }`}
                >
                  {data.item.phase}
                </span>
                <span className="rounded border border-cyan-500/20 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-400">
                  {data.item.repository}
                </span>
                <span className="rounded border border-secondary/30 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-secondary">
                  {data.item.sourceType === "Issue" ? "Issue" : "Chat"}
                </span>
                {data.item.verdict !== null && (
                  <span className="rounded border border-warning/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning">
                    {data.item.verdict}
                  </span>
                )}
              </div>

              {data.item.message !== "" && (
                <p className="text-sm text-slate-400">{data.item.message}</p>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={action.isPending}
                  onClick={() => run("approve")}
                  className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-base shadow-glow transition hover:bg-cyan-300 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Approve
                </button>
                <button
                  type="button"
                  disabled={action.isPending}
                  onClick={() => run("retry")}
                  className="inline-flex items-center gap-1.5 rounded-md border border-cyan-500/30 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-accent/60 hover:text-accent disabled:opacity-50"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Retry
                </button>
                <button
                  type="button"
                  disabled={action.isPending}
                  onClick={() => run("cancel")}
                  className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-50"
                >
                  <Ban className="h-3.5 w-3.5" />
                  Cancel
                </button>
                {data.item.prUrl !== "" && (
                  <a
                    href={data.item.prUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md border border-secondary/40 px-3 py-1.5 text-xs font-semibold text-secondary transition hover:bg-secondary/10"
                  >
                    <GitPullRequest className="h-3.5 w-3.5" />
                    Open PR
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              {action.isError && (
                <p className="text-xs text-danger">
                  Action failed:{" "}
                  {action.error instanceof Error ? action.error.message : "unknown error"}
                </p>
              )}

              <section>
                <h3 className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">
                  Phase timeline
                </h3>
                {data.history.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-600">No events recorded yet.</p>
                ) : (
                  <ol className="mt-3 space-y-0 border-l border-cyan-500/20 pl-4">
                    {data.history.map((event, index) => (
                      <li key={`${event.subject}-${event.time}-${index}`} className="relative pb-4">
                        <span className="absolute top-1 -left-[21.5px] h-2.5 w-2.5 rounded-full border border-accent/60 bg-panel" />
                        <p className="font-mono text-[11px] uppercase tracking-wider text-slate-300">
                          {shortSubject(event.subject)}
                        </p>
                        <p className="font-mono text-[10px] text-slate-600">
                          {formatTimestamp(event.time)}
                        </p>
                        {eventMessage(event) !== "" && (
                          <p className="mt-0.5 text-xs text-slate-500">{eventMessage(event)}</p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="space-y-2">
                <JsonSection label="Status JSON" value={data.status} />
                <JsonSection label="Spec JSON" value={data.spec} />
              </section>
            </>
          )}
        </div>
      </motion.aside>
    </>
  );
}
