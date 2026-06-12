import { describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import type { BoardItem, EventEnvelope } from "@jarvis/events";
import { applyEvent } from "../events/applyEvent";

function makeItem(overrides: Partial<BoardItem> = {}): BoardItem {
  return {
    name: "wi-100",
    repository: "demo-repo",
    title: "Fix login bug",
    sourceType: "Issue",
    phase: "Analyzing",
    message: "analysis in progress",
    verdict: null,
    prUrl: "",
    failed: false,
    createdAt: "2026-06-12T08:00:00Z",
    updatedAt: "2026-06-12T08:30:00Z",
    ...overrides,
  };
}

function makeEnvelope(type: string, data: Record<string, unknown>): EventEnvelope {
  return {
    id: "evt-1",
    type,
    source: "test",
    time: "2026-06-12T09:00:00Z",
    data,
  };
}

function makeClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("applyEvent", () => {
  it("patches the cached item on phase.changed and invalidates the detail query", () => {
    const client = makeClient();
    client.setQueryData<BoardItem[]>(["workflows"], [makeItem(), makeItem({ name: "wi-200" })]);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    applyEvent(
      client,
      makeEnvelope("jarvis.workflow.phase.changed", {
        name: "wi-100",
        repository: "demo-repo",
        fromPhase: "Analyzing",
        toPhase: "Developing",
        message: "writing code",
      }),
    );

    const items = client.getQueryData<BoardItem[]>(["workflows"]);
    const patched = items?.find((item) => item.name === "wi-100");
    expect(patched?.phase).toBe("Developing");
    expect(patched?.message).toBe("writing code");
    expect(patched?.updatedAt).toBe("2026-06-12T09:00:00Z");
    // other items untouched
    expect(items?.find((item) => item.name === "wi-200")?.phase).toBe("Analyzing");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflows", "wi-100"] });
  });

  it("marks the item failed when the new phase is Failed", () => {
    const client = makeClient();
    client.setQueryData<BoardItem[]>(["workflows"], [makeItem()]);

    applyEvent(
      client,
      makeEnvelope("jarvis.workflow.phase.changed", {
        name: "wi-100",
        repository: "demo-repo",
        fromPhase: "Developing",
        toPhase: "Failed",
        message: "CI exploded",
      }),
    );

    const patched = client.getQueryData<BoardItem[]>(["workflows"])?.[0];
    expect(patched?.phase).toBe("Failed");
    expect(patched?.failed).toBe(true);
  });

  it("invalidates the workflows list for lifecycle events", () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    applyEvent(
      client,
      makeEnvelope("jarvis.workflow.created", {
        name: "wi-300",
        namespace: "jarvis",
        repository: "demo-repo",
        sourceType: "Issue",
        title: "New work",
      }),
    );

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflows"] });
  });

  it("invalidates tasks and drafts for email events", () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    applyEvent(client, makeEnvelope("jarvis.email.task.created", {}));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["tasks"] });

    applyEvent(client, makeEnvelope("jarvis.email.draft.ready", {}));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["drafts"] });
  });

  it("invalidates workflows and the chat session for chat.request.created", () => {
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    applyEvent(
      client,
      makeEnvelope("jarvis.chat.request.created", {
        sessionId: "sess-1",
        workflowName: "wi-400",
        repository: "demo-repo",
        title: "Chat request",
      }),
    );

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflows"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["chat", "sess-1"] });
  });

  it("ignores unknown event types silently", () => {
    const client = makeClient();
    const before = [makeItem()];
    client.setQueryData<BoardItem[]>(["workflows"], before);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    applyEvent(client, makeEnvelope("jarvis.something.else.entirely", { hello: "world" }));

    expect(invalidate).not.toHaveBeenCalled();
    expect(client.getQueryData<BoardItem[]>(["workflows"])).toEqual(before);
  });

  it("ignores phase.changed envelopes with malformed payloads", () => {
    const client = makeClient();
    const before = [makeItem()];
    client.setQueryData<BoardItem[]>(["workflows"], before);

    applyEvent(client, makeEnvelope("jarvis.workflow.phase.changed", { nope: true }));

    expect(client.getQueryData<BoardItem[]>(["workflows"])).toEqual(before);
  });
});
