import { useSocketStatus, type SocketStatus } from "../events/socket";

const STATUS_LABEL: Record<SocketStatus, string> = {
  online: "Link online",
  connecting: "Linking…",
  offline: "Link offline",
};

const ORB_CLASS: Record<SocketStatus, string> = {
  online: "bg-accent shadow-glow animate-pulse",
  connecting: "bg-warning",
  offline: "bg-danger",
};

export function ConnectionOrb() {
  const status = useSocketStatus();
  return (
    <div className="flex items-center gap-2.5" title={`WebSocket: ${status}`}>
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${ORB_CLASS[status]}`} />
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
        {STATUS_LABEL[status]}
      </span>
    </div>
  );
}
