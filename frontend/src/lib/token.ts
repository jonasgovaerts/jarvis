import { useSyncExternalStore } from "react";

const STORAGE_KEY = "jarvis_token";

type Listener = () => void;
const listeners = new Set<Listener>();

let unauthorized = false;

function emit(): void {
  for (const listener of listeners) listener();
}

export function getToken(): string {
  return localStorage.getItem(STORAGE_KEY) ?? "";
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY);
  emit();
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
  unauthorized = false;
  emit();
}

export function isUnauthorized(): boolean {
  return unauthorized;
}

/** Flagged by the API client on a 401 response; surfaces the token prompt. */
export function markUnauthorized(): void {
  if (!unauthorized) {
    unauthorized = true;
    emit();
  }
}

export function subscribeAuth(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export interface AuthState {
  token: string;
  unauthorized: boolean;
  needsToken: boolean;
}

export function useAuthState(): AuthState {
  const token = useSyncExternalStore(subscribeAuth, getToken);
  const denied = useSyncExternalStore(subscribeAuth, isUnauthorized);
  return { token, unauthorized: denied, needsToken: token === "" || denied };
}
