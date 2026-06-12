import { useState, type FormEvent } from "react";
import { KeyRound, Plus, Save, Trash2 } from "lucide-react";
import { useAddRepo, useDeleteRepo, useRepos } from "../lib/queries";
import { setToken, useAuthState } from "../lib/token";
import { ConnectionOrb } from "../components/ConnectionOrb";
import { EmptyState } from "../components/EmptyState";

const APP_VERSION = "0.1.0";

const EMPTY_FORM = {
  name: "",
  owner: "",
  repo: "",
  requireLabels: "",
  credentialsSecretName: "",
};

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-cyan-500/15 bg-panel p-5">
      <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.25em] text-slate-400">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function TokenSection() {
  const { token } = useAuthState();
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);

  const save = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed === "") return;
    setToken(trimmed);
    setValue("");
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <form onSubmit={save} className="flex flex-wrap items-center gap-3">
      <KeyRound className="h-4 w-4 text-accent" />
      <input
        type="password"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={token !== "" ? "Token stored — paste to replace" : "Paste bearer token"}
        className="min-w-0 flex-1 rounded-md border border-cyan-500/20 bg-base px-3 py-2 font-mono text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
      />
      <button
        type="submit"
        disabled={value.trim() === ""}
        className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-semibold text-base shadow-glow transition hover:bg-cyan-300 disabled:opacity-50 disabled:shadow-none"
      >
        <Save className="h-3.5 w-3.5" />
        Save token
      </button>
      {saved && (
        <span className="font-mono text-[10px] uppercase tracking-wider text-accent">Saved</span>
      )}
    </form>
  );
}

function ReposSection() {
  const { data: repos, isLoading } = useRepos();
  const addRepo = useAddRepo();
  const deleteRepo = useDeleteRepo();
  const [form, setForm] = useState(EMPTY_FORM);

  const set = (field: keyof typeof EMPTY_FORM) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((previous) => ({ ...previous, [field]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.name.trim() === "" || form.owner.trim() === "" || form.repo.trim() === "") return;
    addRepo.mutate(
      {
        name: form.name.trim(),
        provider: "github",
        owner: form.owner.trim(),
        repo: form.repo.trim(),
        requireLabels: form.requireLabels
          .split(",")
          .map((label) => label.trim())
          .filter((label) => label !== ""),
        credentialsSecretName: form.credentialsSecretName.trim(),
      },
      { onSuccess: () => setForm(EMPTY_FORM) },
    );
  };

  const remove = (name: string) => {
    if (window.confirm(`Remove repository "${name}" from Jarvis management?`)) {
      deleteRepo.mutate(name);
    }
  };

  return (
    <div className="space-y-5">
      {isLoading ? (
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Loading…</p>
      ) : (repos ?? []).length === 0 ? (
        <EmptyState title="No managed repositories" hint="Connect a repository below." compact />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-cyan-500/15 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
                <th className="py-2 pr-4 font-medium">Name</th>
                <th className="py-2 pr-4 font-medium">Source</th>
                <th className="py-2 pr-4 font-medium">Labels</th>
                <th className="py-2 pr-4 font-medium">Active</th>
                <th className="py-2 pr-4 font-medium">State</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {(repos ?? []).map((repo) => (
                <tr key={repo.name} className="border-b border-cyan-500/10">
                  <td className="py-2.5 pr-4 font-mono text-xs text-accent">{repo.name}</td>
                  <td className="py-2.5 pr-4 text-xs text-slate-300">
                    {repo.provider}:{repo.owner}/{repo.repo}
                  </td>
                  <td className="py-2.5 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {(repo.requireLabels ?? []).length === 0 ? (
                        <span className="text-xs text-slate-600">—</span>
                      ) : (
                        (repo.requireLabels ?? []).map((label) => (
                          <span
                            key={label}
                            className="rounded border border-cyan-500/20 px-1.5 py-0.5 font-mono text-[9px] text-slate-400"
                          >
                            {label}
                          </span>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-slate-300">
                    {repo.activeWorkItems}
                  </td>
                  <td className="py-2.5 pr-4">
                    {repo.suspended ? (
                      <span className="rounded border border-warning/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-warning">
                        Suspended
                      </span>
                    ) : (
                      <span className="rounded border border-accent/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent">
                        Active
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-right">
                    <button
                      type="button"
                      onClick={() => remove(repo.name)}
                      disabled={deleteRepo.isPending}
                      title={`Delete ${repo.name}`}
                      className="rounded p-1.5 text-slate-500 transition hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={submit} className="rounded-md border border-cyan-500/15 bg-base/40 p-4">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">
          Connect repository
        </h3>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <input
            value={form.name}
            onChange={set("name")}
            placeholder="Name (k8s resource)"
            className="rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
          />
          <input
            value={form.owner}
            onChange={set("owner")}
            placeholder="Owner / org"
            className="rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
          />
          <input
            value={form.repo}
            onChange={set("repo")}
            placeholder="Repository"
            className="rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
          />
          <input
            value={form.requireLabels}
            onChange={set("requireLabels")}
            placeholder="Required labels (comma separated)"
            className="rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
          />
          <input
            value={form.credentialsSecretName}
            onChange={set("credentialsSecretName")}
            placeholder="Credentials secret name"
            className="rounded-md border border-cyan-500/20 bg-base px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={addRepo.isPending}
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-semibold text-base shadow-glow transition hover:bg-cyan-300 disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            Add repository
          </button>
        </div>
        {addRepo.isError && (
          <p className="mt-2 text-xs text-danger">
            Failed to add:{" "}
            {addRepo.error instanceof Error ? addRepo.error.message : "unknown error"}
          </p>
        )}
      </form>
    </div>
  );
}

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-5 p-3 md:p-6">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-[0.3em] text-slate-200">
        Systems configuration
      </h1>

      <SectionCard title="Managed repositories">
        <ReposSection />
      </SectionCard>

      <SectionCard title="Access token">
        <TokenSection />
      </SectionCard>

      <SectionCard title="Connection">
        <ConnectionOrb />
      </SectionCard>

      <footer className="pt-2 text-center font-mono text-[10px] uppercase tracking-[0.3em] text-slate-600">
        Jarvis UI v{APP_VERSION}
      </footer>
    </div>
  );
}
