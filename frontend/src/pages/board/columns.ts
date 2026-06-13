import type { BoardItem } from "@jarvis/events";

export const COLUMNS = [
  "Queued",
  "Analyzing",
  "Awaiting Approval",
  "Developing",
  "CI",
  "Awaiting Merge",
  "Rollout",
  "Done",
] as const;

export type ColumnId = (typeof COLUMNS)[number];

const PHASE_TO_COLUMN: Record<BoardItem["phase"], ColumnId | null> = {
  Pending: "Queued",
  Analyzing: "Analyzing",
  AwaitingDevApproval: "Awaiting Approval",
  Developing: "Developing",
  AwaitingCI: "CI",
  AwaitingMerge: "Awaiting Merge",
  RolloutCheck: "Rollout",
  Succeeded: "Done",
  Skipped: "Done",
  Failed: null, // failed items live in the "Needs attention" strip
};

export const DONE_WINDOW_MS = 48 * 60 * 60 * 1000;

export interface GroupedBoard {
  byColumn: Map<ColumnId, BoardItem[]>;
  needsAttention: BoardItem[];
}

function itemTimestamp(item: BoardItem): number {
  return new Date(item.updatedAt ?? item.createdAt).getTime();
}

/**
 * Split board items into columns plus the failed "Needs attention" strip.
 * Done items older than 48h are hidden client-side.
 */
export function groupItems(items: BoardItem[], now = Date.now()): GroupedBoard {
  const byColumn = new Map<ColumnId, BoardItem[]>(COLUMNS.map((column) => [column, []]));
  const needsAttention: BoardItem[] = [];

  for (const item of items) {
    if (item.phase === "Failed" || item.failed) {
      needsAttention.push(item);
      continue;
    }
    const column = PHASE_TO_COLUMN[item.phase];
    if (column === null) continue;
    if (column === "Done" && now - itemTimestamp(item) > DONE_WINDOW_MS) continue;
    byColumn.get(column)?.push(item);
  }

  for (const list of byColumn.values()) {
    list.sort((a, b) => itemTimestamp(b) - itemTimestamp(a));
  }
  needsAttention.sort((a, b) => itemTimestamp(b) - itemTimestamp(a));

  return { byColumn, needsAttention };
}
