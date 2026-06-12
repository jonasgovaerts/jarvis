import { useSyncExternalStore } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { parseEnvelope } from "@jarvis/events";
import { getToken, subscribeAuth } from "../lib/token";
import { applyEvent } from "./applyEvent";

export type SocketStatus = "online" | "connecting" | "offline";

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;

let socket: WebSocket | null = null;
let client: QueryClient | null = null;
let started = false;
let attempts = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let currentToken = "";
let status: SocketStatus = "offline";

const statusListeners = new Set<() => void>();

function setStatus(next: SocketStatus): void {
  if (status === next) return;
  status = next;
  for (const listener of statusListeners) listener();
}

export function getSocketStatus(): SocketStatus {
  return status;
}

export function subscribeSocketStatus(listener: () => void): () => void {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
}

export function useSocketStatus(): SocketStatus {
  return useSyncExternalStore(subscribeSocketStatus, getSocketStatus);
}

let authMode = "token";

/** Called by the app once /api/features resolves; reconnects if needed. */
export function setAuthMode(mode: string): void {
  if (mode === authMode) return;
  authMode = mode;
  if (started) reconnectNow();
}

/** Start the single module-level WebSocket connection (idempotent). */
export function startSocket(queryClient: QueryClient): void {
  client = queryClient;
  if (started) return;
  started = true;
  // Reconnect with the new credentials whenever the token changes.
  subscribeAuth(() => {
    if (getToken() !== currentToken) {
      reconnectNow();
    }
  });
  connect();
}

function reconnectNow(): void {
  attempts = 0;
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket !== null) {
    const old = socket;
    socket = null;
    old.onclose = null;
    old.onmessage = null;
    old.onerror = null;
    old.close();
  }
  connect();
}

function connect(): void {
  if (typeof WebSocket === "undefined") return;
  const token = getToken();
  currentToken = token;
  if (token === "" && authMode !== "forward-auth") {
    setStatus("offline");
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  // forward-auth: the authentik session cookie authenticates the upgrade.
  const query = token === "" ? "" : `?token=${encodeURIComponent(token)}`;
  const url = `${protocol}://${window.location.host}/ws${query}`;
  setStatus("connecting");

  const ws = new WebSocket(url);
  socket = ws;

  ws.onopen = () => {
    if (socket !== ws) return;
    attempts = 0;
    setStatus("online");
  };
  ws.onmessage = (event: MessageEvent) => {
    if (typeof event.data === "string") {
      handleMessage(event.data);
    }
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    socket = null;
    setStatus("offline");
    scheduleReconnect();
  };
  ws.onerror = () => {
    ws.close();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimer !== null) return;
  const delay = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** attempts);
  attempts += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function handleMessage(raw: string): void {
  if (client === null) return;
  let message: unknown;
  try {
    message = JSON.parse(raw);
  } catch {
    return;
  }
  if (typeof message !== "object" || message === null) return;
  const { type } = message as { type?: unknown };

  if (type === "ping") {
    socket?.send(JSON.stringify({ type: "pong" }));
    return;
  }
  if (type === "hello") {
    // Covers any events missed while disconnected.
    void client.invalidateQueries();
    return;
  }
  if (type === "event") {
    const envelope = parseEnvelope((message as { event?: unknown }).event);
    if (envelope !== null) {
      applyEvent(client, envelope);
    }
  }
}
