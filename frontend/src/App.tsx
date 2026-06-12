import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./components/AppShell";
import { TokenGate } from "./components/TokenGate";
import { BoardPage } from "./pages/board/BoardPage";
import { WorkflowDetailPanel } from "./pages/board/WorkflowDetailPanel";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { setAuthMode, startSocket } from "./events/socket";
import { useFeatures } from "./lib/queries";
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

function AuthModeSync() {
  const { data: features } = useFeatures();
  useEffect(() => {
    if (features) setAuthMode(features.auth);
  }, [features]);
  return null;
}

export default function App() {
  useEffect(() => {
    startSocket(queryClient);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthModeSync />
      <BrowserRouter>
        <TokenGate />
        <AppShell>
          <Routes>
            <Route path="/" element={<BoardPage />}>
              <Route path="workflows/:name" element={<WorkflowDetailPanel />} />
            </Route>
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
