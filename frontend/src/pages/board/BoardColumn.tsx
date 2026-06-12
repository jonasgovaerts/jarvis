import type { BoardItem } from "@jarvis/events";
import { EmptyState } from "../../components/EmptyState";
import { WorkflowCard } from "./WorkflowCard";
import type { ColumnId } from "./columns";

interface BoardColumnProps {
  title: ColumnId;
  items: BoardItem[];
}

export function BoardColumn({ title, items }: BoardColumnProps) {
  return (
    <section
      data-testid={`column-${title}`}
      className="flex w-full shrink-0 flex-col rounded-lg border border-cyan-500/15 border-t-2 border-t-accent/50 bg-panel/50 md:w-64"
    >
      <header className="flex items-center justify-between px-3 py-2.5">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
          {title}
        </h2>
        <span className="min-w-6 rounded-full bg-cyan-500/10 px-2 py-0.5 text-center font-mono text-[10px] text-accent">
          {items.length}
        </span>
      </header>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {items.length === 0 ? (
          <EmptyState title="Standby" compact />
        ) : (
          items.map((item) => <WorkflowCard key={item.name} item={item} />)
        )}
      </div>
    </section>
  );
}
