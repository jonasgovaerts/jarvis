import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { setToken, useAuthState } from "../lib/token";

/**
 * Full-screen prompt shown on first run (no token stored) or after a 401.
 */
export function TokenGate() {
  const { needsToken, unauthorized } = useAuthState();
  const [value, setValue] = useState("");
  const queryClient = useQueryClient();

  if (!needsToken) return null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed === "") return;
    setToken(trimmed);
    setValue("");
    void queryClient.invalidateQueries();
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-base/85 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-lg border border-cyan-500/20 bg-panel p-6 shadow-glow"
      >
        <div className="flex items-center gap-3">
          <KeyRound className="h-5 w-5 text-accent" />
          <h2 className="font-mono text-xs font-semibold uppercase tracking-[0.25em] text-accent">
            Access token required
          </h2>
        </div>
        <p className="mt-3 text-xs text-slate-400">
          {unauthorized
            ? "The gateway rejected your token (401). Enter a valid bearer token to continue."
            : "Enter your Jarvis gateway bearer token to bring systems online."}
        </p>
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Bearer token"
          className="mt-4 w-full rounded-md border border-cyan-500/20 bg-base px-3 py-2 font-mono text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
        />
        <button
          type="submit"
          className="mt-4 w-full rounded-md bg-accent px-3 py-2 text-sm font-semibold text-base shadow-glow transition hover:bg-cyan-300"
        >
          Authenticate
        </button>
      </form>
    </div>
  );
}
