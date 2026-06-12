import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";
import { LayoutDashboard, ListChecks, Menu, MessageSquare, Settings } from "lucide-react";
import { Clock } from "./Clock";
import { ConnectionOrb } from "./ConnectionOrb";
import { useFeatures } from "../lib/queries";

const NAV_ITEMS = [
  { to: "/", label: "Board", icon: LayoutDashboard, end: true },
  { to: "/tasks", label: "Tasks", icon: ListChecks, end: false, feature: "mail" },
  { to: "/chat", label: "Chat", icon: MessageSquare, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { data: features } = useFeatures();
  const navItems = NAV_ITEMS.filter(
    (item) => !("feature" in item) || features?.[item.feature] !== false,
  );

  const sidebar = (
    <>
      <div className="px-5 pt-6 pb-5">
        <span className="font-mono text-lg font-semibold uppercase tracking-[0.35em] text-accent">
          Jarvis
        </span>
        <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.25em] text-slate-500">
          Mission Control
        </p>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setSidebarOpen(false)}
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
      <div className="flex items-center justify-between border-t border-cyan-500/15 p-4">
        <Clock />
        <ConnectionOrb />
      </div>
    </>
  );

  return (
    <div className="flex h-full overflow-hidden">
      <aside className="hidden w-52 shrink-0 flex-col border-r border-cyan-500/15 bg-panel/70 md:flex">
        {sidebar}
      </aside>
      <div
        className={`fixed inset-y-0 left-0 z-20 w-52 transform transition-transform duration-300 md:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col border-r border-cyan-500/15 bg-panel">{sidebar}</div>
      </div>
      {sidebarOpen ? (
        <div
          aria-hidden
          className="fixed inset-0 z-10 bg-black/30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="flex items-center p-2 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded p-1 text-slate-400"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
        {children}
      </main>
    </div>
  );
}
