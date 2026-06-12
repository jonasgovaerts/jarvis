import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { clearToken, setToken } from "./token";

let manager: UserManager | null = null;

/** Build (once) the OIDC client from the gateway-provided authority. */
export function initOidc(issuer: string, clientId: string): UserManager {
  if (manager !== null) return manager;
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

/** Boot: restore an existing session or start the redirect dance. */
export async function ensureSignedIn(): Promise<void> {
  if (manager === null) throw new Error("initOidc must run first");
  const user = await manager.getUser();
  if (user !== null && !user.expired) {
    syncToken(user);
    return;
  }
  await manager.signinRedirect();
}

/** /auth/callback handler; returns the post-login path to navigate to. */
export async function completeSignIn(): Promise<string> {
  if (manager === null) throw new Error("initOidc must run first");
  const user = await manager.signinRedirectCallback();
  syncToken(user);
  return "/";
}

/** Re-authenticate after a 401 (expired/revoked session). */
export function reauthenticate(): void {
  void manager?.signinRedirect();
}
