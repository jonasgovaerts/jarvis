import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./components/AppShell";
import { TokenGate } from "./components/TokenGate";
import { BoardPage } from "./pages/board/BoardPage";
import { WorkflowDetailPanel } from "./pages/board/WorkflowDetailPanel";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { startSocket } from "./events/socket";
import { useFeatures } from "./lib/queries";
import { completeSignIn, ensureSignedIn, initOidc } from "./lib/oidc";
import { ApiError } from "./lib/api";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
          return false;
        }
        return failureCount < 2;
      },
    },
  },
});

function OidcBoot() {
  const { data: features } = useFeatures();
  useEffect(() => {
    if (features?.auth !== "oidc" || features.oidcIssuer === "") return;
    initOidc(features.oidcIssuer, features.oidcClientId);
    // The callback route finishes its own dance; don't start a second one.
    if (window.location.pathname !== "/auth/callback") {
      void ensureSignedIn();
    }
  }, [features]);
  return null;
}

function AuthCallback() {
  const navigate = useNavigate();
  const { data: features } = useFeatures();
  const [error, setError] = useState("");
  useEffect(() => {
    if (features?.auth !== "oidc" || features.oidcIssuer === "") return;
    initOidc(features.oidcIssuer, features.oidcClientId);
    completeSignIn()
      .then((path) => navigate(path, { replace: true }))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [features, navigate]);
  if (error !== "") {
    return (
      <div className="grid h-full place-items-center">
        <div className="max-w-md text-center">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-danger">Sign-in failed</p>
          <p className="mt-3 text-sm text-slate-400">{error}</p>
          <p className="mt-2 text-xs text-slate-600">
            Check the authentik provider: public client type, redirect URI, scopes.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="grid h-full place-items-center font-mono text-xs uppercase tracking-[0.3em] text-slate-500">
      Completing sign-in…
    </div>
  );
}

export default function App() {
  useEffect(() => {
    startSocket(queryClient);

    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("/sw.js")
          .then((registration) => {
            console.log("SW registered: ", registration);
          })
          .catch((registrationError) => {
            console.log("SW registration failed: ", registrationError);
          });
      });
    }
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <OidcBoot />
      <BrowserRouter>
        <TokenGate />
        <AppShell>
          <Routes>
            <Route path="/" element={<BoardPage />}>
              <Route path="workflows/:name" element={<WorkflowDetailPanel />} />
            </Route>
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
