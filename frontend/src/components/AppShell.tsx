import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";
import {
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  Settings,
  X,
} from "lucide-react";
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
  const { data: features } = useFeatures();
  const [isNavOpen, setIsNavOpen] = useState(false);
  const navItems = NAV_ITEMS.filter(
    (item) => !("feature" in item) || features?.[item.feature] !== false,
  );
  const closeNav = () => setIsNavOpen(false);

  return (
    <div className="flex h-full overflow-hidden">
      {isNavOpen && (
        <div
          className="fixed inset-0 z-30 bg-base/60 backdrop-blur-[2px] md:hidden"
          onClick={closeNav}
          aria-hidden
        />
      )}
      <aside
        className={`${
          isNavOpen ? "flex" : "hidden"
        } fixed inset-y-0 left-0 z-40 w-60 flex-col border-r border-cyan-500/15 bg-panel md:relative md:z-auto md:flex md:w-52 md:bg-panel/70`}
      >
        <div className="flex items-start justify-between px-5 pt-6 pb-5">
          <div>
            <span className="font-mono text-lg font-semibold uppercase tracking-[0.35em] text-accent">
              Jarvis
            </span>
            <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.25em] text-slate-500">
              Mission Control
            </p>
          </div>
          <button
            type="button"
            onClick={closeNav}
            aria-label="Close navigation"
            className="rounded p-1 text-slate-500 transition hover:bg-cyan-500/10 hover:text-slate-200 md:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={closeNav}
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
        <div className="px-3 pb-2">
          <a
            href="https://authentik.jonasg.be/flows/user/logout/"
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-cyan-500/5 hover:text-slate-200"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span>Logout</span>
          </a>
        </div>
        <div className="flex items-center justify-between border-t border-cyan-500/15 p-4">
          <Clock />
          <ConnectionOrb />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-cyan-500/15 px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={() => setIsNavOpen(true)}
            aria-label="Open navigation"
            className="rounded p-1 text-accent transition hover:bg-cyan-500/10"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-mono text-sm font-semibold uppercase tracking-[0.3em] text-accent">
            Jarvis
          </span>
          <div className="ml-auto">
            <ConnectionOrb />
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
