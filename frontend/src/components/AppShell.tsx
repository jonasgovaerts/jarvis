import type { ReactNode } from "react";
import { NavLink } from "react-router";
import { LayoutDashboard, ListChecks, MessageSquare, Settings } from "lucide-react";
import { ConnectionOrb } from "./ConnectionOrb";

const NAV_ITEMS = [
  { to: "/", label: "Board", icon: LayoutDashboard, end: true },
  { to: "/tasks", label: "Tasks", icon: ListChecks, end: false },
  { to: "/chat", label: "Chat", icon: MessageSquare, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full overflow-hidden">
      <aside className="flex w-52 shrink-0 flex-col border-r border-cyan-500/15 bg-panel/70">
        <div className="px-5 pt-6 pb-5">
          <span className="font-mono text-lg font-semibold uppercase tracking-[0.35em] text-accent">
            Jarvis
          </span>
          <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.25em] text-slate-500">
            Mission Control
          </p>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-cyan-500/10 text-accent"
                    : "text-slate-400 hover:bg-cyan-500/5 hover:text-slate-200"
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-cyan-500/15 p-4">
          <ConnectionOrb />
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
