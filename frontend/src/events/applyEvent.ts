import type { QueryClient } from "@tanstack/react-query";
import {
  ChatRequestCreatedSchema,
  WorkflowPhaseChangedSchema,
  type BoardItem,
  type EventEnvelope,
} from "@jarvis/events";

/**
 * Apply one validated event envelope to the TanStack Query cache.
 * Unknown event types are ignored silently (forward compatibility).
 */
export function applyEvent(queryClient: QueryClient, envelope: EventEnvelope): void {
  switch (envelope.type) {
    case "jarvis.workflow.phase.changed": {
      const parsed = WorkflowPhaseChangedSchema.safeParse(envelope.data);
      if (!parsed.success) return;
      const { name, toPhase, message } = parsed.data;
      queryClient.setQueryData<BoardItem[]>(["workflows"], (old) =>
        old?.map((item) =>
          item.name === name
            ? {
                ...item,
                phase: toPhase,
                message,
                failed: toPhase === "Failed" ? true : item.failed,
                updatedAt: envelope.time,
              }
            : item,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["workflows", name] });
      return;
    }
    case "jarvis.workflow.created":
    case "jarvis.workflow.failed":
    case "jarvis.workflow.pr.opened":
    case "jarvis.workflow.pr.ready":
    case "jarvis.workflow.rollout.completed": {
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
      return;
    }
    case "jarvis.email.task.created": {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      return;
    }
    case "jarvis.email.draft.ready": {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
      return;
    }
    case "jarvis.chat.request.created": {
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
      const parsed = ChatRequestCreatedSchema.safeParse(envelope.data);
      if (parsed.success) {
        void queryClient.invalidateQueries({ queryKey: ["chat", parsed.data.sessionId] });
      }
      return;
    }
    default:
      // Unknown event type — ignore.
      return;
  }
}
