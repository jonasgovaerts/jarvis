import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { MessageSquarePlus, Radar, Send } from "lucide-react";
import type { ChatMessage, ChatSession } from "@jarvis/events";
import { useChatMessages, useChatSessions, useCreateSession, useSendMessage, useUpdateSessionTitle } from "../lib/queries";
import { EmptyState } from "../components/EmptyState";
import { formatAge } from "../lib/time";

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-lg border px-3 py-2 text-sm ${
          isUser
            ? "border-accent/25 bg-cyan-500/10 text-slate-100"
            : "border-cyan-500/15 bg-panel text-slate-300"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.workflowName !== "" && (
          <Link
            to={`/workflows/${encodeURIComponent(message.workflowName)}`}
            className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent transition hover:bg-cyan-500/20"
          >
            <Radar className="h-3 w-3" />
            Tracking {message.workflowName}
          </Link>
        )}
        <p
          className={`mt-1 font-mono text-[9px] ${isUser ? "text-cyan-200/40" : "text-slate-600"}`}
        >
          {formatAge(message.createdAt)} ago
        </p>
      </div>
    </div>
  );
}

function SessionItem({
  session,
  isActive,
  onClick,
}: {
  session: ChatSession;
  isActive: boolean;
  onClick: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(session.title);
  const updateTitle = useUpdateSessionTitle();

  const handleSave = () => {
    if (title.trim() && title !== session.title) {
      updateTitle.mutate({ sessionId: session.id, title: title.trim() });
    }
    setIsEditing(false);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
      handleSave();
    } else if (event.key === "Escape") {
      setIsEditing(false);
      setTitle(session.title);
    }
  };

  if (isEditing) {
    return (
      <div
        className={`block w-full rounded-md px-3 py-2 text-left text-sm transition ${
          isActive
            ? "bg-cyan-500/10 text-accent"
            : "text-slate-400 bg-cyan-500/5"
        }`}
      >
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={handleSave}
          onKeyDown={handleKeyDown}
          className="w-full border-0 bg-transparent p-0 text-sm text-slate-200 focus:outline-none"
          autoFocus
        />
        <span className="font-mono text-[9px] text-slate-600">
          {formatAge(session.createdAt)} ago
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      onDoubleClick={() => {
        setIsEditing(true);
      }}
      className={`block w-full rounded-md px-3 py-2 text-left text-sm transition ${
        isActive
          ? "bg-cyan-500/10 text-accent"
          : "text-slate-400 hover:bg-cyan-500/5 hover:text-slate-200"
      }`}
    >
      <span className="block truncate">{session.title || "Untitled session"}</span>
      <span className="font-mono text-[9px] text-slate-600">
        {formatAge(session.createdAt)} ago
      </span>
    </button>
  );
}

export function ChatPage() {
  const { data: sessions, isLoading: sessionsLoading } = useChatSessions();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const activeId = selectedId ?? sessions?.[0]?.id ?? null;

  const { data: messages } = useChatMessages(activeId);
  const createSession = useCreateSession();
  const send = useSendMessage(activeId ?? "");
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages?.length]);

  const newSession = () => {
    createSession.mutate(undefined, {
      onSuccess: (session) => setSelectedId(session.id),
    });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (content === "" || activeId === null || send.isPending) return;
    setDraft("");
    send.mutate(content);
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-cyan-500/15 bg-panel/40">
        <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-3">
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
            Sessions
          </h2>
          <button
            type="button"
            onClick={newSession}
            disabled={createSession.isPending}
            title="New session"
            className="rounded p-1 text-accent transition hover:bg-cyan-500/10 disabled:opacity-50"
          >
            <MessageSquarePlus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2">
          {sessionsLoading ? (
            <p className="px-2 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">
              Loading…
            </p>
          ) : (sessions ?? []).length === 0 ? (
            <p className="px-2 py-2 text-xs text-slate-600">No sessions yet.</p>
          ) : (
            (sessions ?? []).map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === activeId}
                onClick={() => setSelectedId(session.id)}
              />
            ))
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto p-6">
          {activeId === null ? (
            <EmptyState
              title="No transmission channel"
              hint="Create a session to start talking to Jarvis."
            />
          ) : (messages ?? []).length === 0 ? (
            <EmptyState title="Channel open" hint="Send a message to begin." />
          ) : (
            (messages ?? []).map((message) => <MessageBubble key={message.id} message={message} />)
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={submit} className="flex gap-2 border-t border-cyan-500/15 bg-panel/40 p-4">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={activeId === null ? "Create a session first…" : "Message Jarvis…"}
            disabled={activeId === null}
            className="min-w-0 flex-1 rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={activeId === null || send.isPending || draft.trim() === ""}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-base shadow-glow transition hover:bg-cyan-300 disabled:opacity-50 disabled:shadow-none"
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </button>
        </form>
      </section>
    </div>
  );
}
