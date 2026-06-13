import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { clearToken, setToken } from "./token";

let manager: UserManager | null = null;
let authorityOrigin = "";

/** Build (once) the OIDC client from the gateway-provided authority. */
export function initOidc(issuer: string, clientId: string): UserManager {
  if (manager !== null) return manager;
  authorityOrigin = new URL(issuer).origin;
  manager = new UserManager({
    authority: issuer,
    client_id: clientId,
    redirect_uri: `${window.location.origin}/auth/callback`,
    post_logout_redirect_uri: window.location.origin,
    response_type: "code", // + PKCE, automatic for public clients
    scope: "openid profile email offline_access",
    automaticSilentRenew: true, // uses the refresh token when granted
    userStore: new WebStorageStateStore({ store: window.localStorage }),
  });

  // token.ts stays the single transport the API client and socket read from.
  manager.events.addUserLoaded((user) => syncToken(user));
  manager.events.addUserUnloaded(() => clearToken());
  manager.events.addSilentRenewError(() => {
    void manager?.signinRedirect();
  });
  return manager;
}

function syncToken(user: User | null): void {
  if (user !== null && !user.expired && user.access_token) {
    setToken(user.access_token);
  }
}

let redirectStarted = false;

/** Boot: restore an existing session or start the redirect dance. */
export async function ensureSignedIn(): Promise<void> {
  if (manager === null) throw new Error("initOidc must run first");
  const user = await manager.getUser();
  if (user !== null && !user.expired) {
    syncToken(user);
    return;
  }
  if (redirectStarted) return; // one navigation is plenty
  redirectStarted = true;
  await manager.signinRedirect();
}

let callbackResult: Promise<string> | null = null;

/**
 * /auth/callback handler; returns the post-login path to navigate to.
 * Memoized: the exchange consumes a one-time state from storage, and the
 * effect that calls this re-runs when query invalidation (triggered by the
 * freshly-connected socket) refreshes the features object. Re-running the
 * exchange would fail with "No matching state found in storage".
 */
export function completeSignIn(): Promise<string> {
  if (manager === null) throw new Error("initOidc must run first");
  callbackResult ??= manager
    .signinRedirectCallback()
    .then((user) => {
      syncToken(user);
      return "/";
    })
    .catch(async (err: unknown) => {
      // If a concurrent/earlier run already finished the exchange, being
      // signed in wins over the bookkeeping error.
      const user = await manager?.getUser();
      if (user != null && !user.expired) {
        syncToken(user);
        return "/";
      }
      throw err;
    });
  return callbackResult;
}

/** Re-authenticate after a 401 (expired/revoked session). */
export function reauthenticate(): void {
  void manager?.signinRedirect();
}

/**
 * Log out: clear the local OIDC session FIRST (otherwise the SPA reboots
 * straight back in on a still-cached token), then end the authentik session.
 * In token mode (no OIDC manager) just drop the bearer token and reload.
 */
export async function logout(): Promise<void> {
  try {
    await manager?.removeUser(); // also fires addUserUnloaded → clearToken()
    await manager?.clearStaleState();
  } catch {
    // ignore — we redirect regardless
  }
  clearToken();
  window.location.href = authorityOrigin
    ? `${authorityOrigin}/flows/user/logout/`
    : "/";
}
