import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { BoardItem } from "@jarvis/events";
import { BoardColumn } from "../pages/board/BoardColumn";
import { DONE_WINDOW_MS, groupItems } from "../pages/board/columns";

// WorkflowCard uses React Query (useDeleteWorkflow), so rendering a column
// needs a client in scope.
function renderColumn(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeItem(overrides: Partial<BoardItem> = {}): BoardItem {
  return {
    name: "wi-1",
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

describe("BoardColumn", () => {
  it("renders the column title, count badge and cards", () => {
    const items = [
      makeItem(),
      makeItem({ name: "wi-2", title: "Add dark mode", sourceType: "FeatureRequest" }),
    ];
    renderColumn(<BoardColumn title="Analyzing" items={items} />);

    expect(screen.getByText("Analyzing")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Fix login bug")).toBeTruthy();
    expect(screen.getByText("Add dark mode")).toBeTruthy();
    expect(screen.getAllByText("demo-repo")).toHaveLength(2);
  });

  it("renders a HUD empty placeholder when there are no items", () => {
    renderColumn(<BoardColumn title="Rollout" items={[]} />);

    expect(screen.getByText("Rollout")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy();
    expect(screen.getByText("Standby")).toBeTruthy();
  });
});

describe("groupItems", () => {
  const now = new Date("2026-06-12T12:00:00Z").getTime();

  it("maps phases onto the seven board columns", () => {
    const { byColumn, needsAttention } = groupItems(
      [
        makeItem({ name: "a", phase: "Pending" }),
        makeItem({ name: "b", phase: "AwaitingCI" }),
        makeItem({ name: "c", phase: "AwaitingMerge" }),
        makeItem({ name: "d", phase: "RolloutCheck" }),
        makeItem({ name: "e", phase: "Succeeded", updatedAt: "2026-06-12T11:00:00Z" }),
        makeItem({ name: "f", phase: "Skipped", updatedAt: "2026-06-12T11:00:00Z" }),
      ],
      now,
    );

    expect(byColumn.get("Queued")?.map((item) => item.name)).toEqual(["a"]);
    expect(byColumn.get("CI")?.map((item) => item.name)).toEqual(["b"]);
    expect(byColumn.get("Awaiting Merge")?.map((item) => item.name)).toEqual(["c"]);
    expect(byColumn.get("Rollout")?.map((item) => item.name)).toEqual(["d"]);
    expect(
      byColumn
        .get("Done")
        ?.map((item) => item.name)
        .sort(),
    ).toEqual(["e", "f"]);
    expect(needsAttention).toEqual([]);
  });

  it("routes failed items to the needs-attention strip, not a column", () => {
    const { byColumn, needsAttention } = groupItems(
      [makeItem({ name: "boom", phase: "Failed", failed: true })],
      now,
    );

    expect(needsAttention.map((item) => item.name)).toEqual(["boom"]);
    for (const items of byColumn.values()) {
      expect(items).toEqual([]);
    }
  });

  it("hides Done items older than 48 hours", () => {
    const fresh = new Date(now - DONE_WINDOW_MS / 2).toISOString();
    const stale = new Date(now - DONE_WINDOW_MS - 60_000).toISOString();
    const { byColumn } = groupItems(
      [
        makeItem({ name: "fresh", phase: "Succeeded", updatedAt: fresh }),
        makeItem({ name: "stale", phase: "Succeeded", updatedAt: stale }),
      ],
      now,
    );

    expect(byColumn.get("Done")?.map((item) => item.name)).toEqual(["fresh"]);
  });
});
