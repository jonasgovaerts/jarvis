import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BoardItemSchema,
  ChatMessageSchema,
  ChatSessionSchema,
  DraftEmailSchema,
  RepositoryInfoSchema,
  UserTaskSchema,
  WorkflowEventSchema,
  type BoardItem,
  type ChatMessage,
  type ChatSession,
  type WorkflowEvent,
} from "@jarvis/events";
import { api } from "./api";

export interface WorkflowDetail {
  item: BoardItem;
  spec: unknown;
  status: unknown;
  history: WorkflowEvent[];
}

function parseWorkflowDetail(raw: unknown): WorkflowDetail {
  const record = (raw ?? {}) as {
    item?: unknown;
    spec?: unknown;
    status?: unknown;
    history?: unknown;
  };
  return {
    item: BoardItemSchema.parse(record.item),
    spec: record.spec,
    status: record.status,
    history: WorkflowEventSchema.array().parse(record.history ?? []),
  };
}

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------

export function useWorkflows() {
  return useQuery({
    queryKey: ["workflows"],
    queryFn: async () => BoardItemSchema.array().parse(await api<unknown>("/api/workflows")),
  });
}

export function useWorkflowDetail(name: string) {
  return useQuery({
    queryKey: ["workflows", name],
    queryFn: async () =>
      parseWorkflowDetail(await api<unknown>(`/api/workflows/${encodeURIComponent(name)}`)),
    enabled: name !== "",
  });
}

export type WorkflowAction = "approve" | "retry" | "cancel";

export function useWorkflowAction(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: WorkflowAction) =>
      api<unknown>(`/api/workflows/${encodeURIComponent(name)}/actions`, {
        method: "POST",
        body: { action },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Tasks & drafts
// ---------------------------------------------------------------------------

export type TaskStatusFilter = "open" | "done";

export function useTasks(status: TaskStatusFilter) {
  return useQuery({
    queryKey: ["tasks", status],
    queryFn: async () =>
      UserTaskSchema.array().parse(await api<unknown>(`/api/tasks?status=${status}`)),
  });
}

export function useTaskUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "done" | "open" | "snoozed" }) =>
      api<unknown>(`/api/tasks/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function useDrafts() {
  return useQuery({
    queryKey: ["drafts"],
    queryFn: async () => DraftEmailSchema.array().parse(await api<unknown>("/api/drafts")),
  });
}

export function useDraftAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, action }: { taskId: string; action: "approve" | "discard" }) =>
      api<unknown>(`/api/drafts/${encodeURIComponent(taskId)}/actions`, {
        method: "POST",
        body: { action },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Repositories
// ---------------------------------------------------------------------------

export function useRepos() {
  return useQuery({
    queryKey: ["repos"],
    queryFn: async () => RepositoryInfoSchema.array().parse(await api<unknown>("/api/repos")),
  });
}

export interface NewRepository {
  name: string;
  provider: "github";
  owner: string;
  repo: string;
  requireLabels: string[];
  credentialsSecretName: string;
}

export function useAddRepo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repo: NewRepository) => api<unknown>("/api/repos", { method: "POST", body: repo }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export function useDeleteRepo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api<unknown>(`/api/repos/${encodeURIComponent(name)}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export function useChatSessions() {
  return useQuery({
    queryKey: ["chat", "sessions"],
    queryFn: async () => ChatSessionSchema.array().parse(await api<unknown>("/api/chat/sessions")),
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (title?: string) =>
      ChatSessionSchema.parse(
        await api<unknown>("/api/chat/sessions", {
          method: "POST",
          body: title ? { title } : {},
        }),
      ) as ChatSession,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}

export function chatMessagesKey(sessionId: string): readonly unknown[] {
  return ["chat", sessionId, "messages"];
}

export function useChatMessages(sessionId: string | null) {
  return useQuery({
    queryKey: chatMessagesKey(sessionId ?? ""),
    queryFn: async () =>
      ChatMessageSchema.array().parse(
        await api<unknown>(`/api/chat/sessions/${encodeURIComponent(sessionId ?? "")}/messages`),
      ),
    enabled: sessionId !== null && sessionId !== "",
  });
}

interface SendMessageContext {
  previous: ChatMessage[] | undefined;
}

export function useSendMessage(sessionId: string) {
  const queryClient = useQueryClient();
  const key = chatMessagesKey(sessionId);
  return useMutation<ChatMessage, Error, string, SendMessageContext>({
    mutationFn: async (content: string) =>
      ChatMessageSchema.parse(
        await api<unknown>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
          method: "POST",
          body: { content },
        }),
      ) as ChatMessage,
    onMutate: async (content) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ChatMessage[]>(key);
      const optimistic: ChatMessage = {
        id: `optimistic-${Date.now()}`,
        sessionId,
        role: "user",
        content,
        workflowName: "",
        createdAt: new Date().toISOString(),
      };
      queryClient.setQueryData<ChatMessage[]>(key, (old) => [...(old ?? []), optimistic]);
      return { previous };
    },
    onError: (_error, _content, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(key, context.previous);
      }
    },
    onSuccess: (assistantMessage) => {
      queryClient.setQueryData<ChatMessage[]>(key, (old) => [...(old ?? []), assistantMessage]);
    },
  });
}
