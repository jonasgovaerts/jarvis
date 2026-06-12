import { ReactNode, useState } from "react";
import { NavLink } from "react-router";
import { LayoutDashboard, ListChecks, MessageSquare, Settings, Menu } from "lucide-react";
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
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const { data: features } = useFeatures();
  const navItems = NAV_ITEMS.filter(
    (item) => !("feature" in item) || features?.[item.feature] !== false,
  );

  const sidebarContent = (
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
      {/* Static sidebar for desktop */}
      <aside className="hidden w-52 shrink-0 flex-col border-r border-cyan-500/15 bg-panel/70 md:flex">
        {sidebarContent}
      </aside>

      {/* Mobile navigation */}
      <div className="md:hidden">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="absolute top-4 left-4 z-20 rounded-md bg-panel/50 p-2 text-slate-300 ring-1 ring-inset ring-cyan-500/15"
        >
          <Menu className="h-5 w-5" />
          <span className="sr-only">Open menu</span>
        </button>
        {isSidebarOpen && (
          <div
            className="absolute inset-0 z-30 bg-black/50 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          >
            <aside className="flex h-full w-52 flex-col border-r border-cyan-500/15 bg-panel/95" onClick={(e) => e.stopPropagation()}>
              {sidebarContent}
            </aside>
          </div>
        )}
      </div>

      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
