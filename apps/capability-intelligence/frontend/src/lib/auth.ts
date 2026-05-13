// Google Identity Services — runtime-configured ID token capture.
//
// Flow:
//   1. On boot we call /api/auth/config (no auth required) to learn the
//      project's OAuth client_id + auth_mode + allowed domain.
//   2. If auth_mode = 'google_oauth' AND we don't already hold a token,
//      the SPA renders the Sign-in gate which calls
//      google.accounts.id.initialize({ client_id, callback }).
//   3. The callback receives a JWT (the user's Google ID token); we
//      store it in sessionStorage + memory and reload the queries.
//   4. apiGet / apiPost read this token instead of the dev fallback.
//
// `apiPost` and `apiGet` import currentToken() — if it returns null we
// fall back to the legacy `dev-mishley.otiende@zennify.com` token so
// dev mode keeps working.

import { create } from 'zustand';

export type AuthConfig = {
  auth_mode: 'dev' | 'firebase' | 'google_oauth';
  google_oauth_client_id: string | null;
  allowed_domain: string;
  redirect_uris: string[];
};

type AuthState = {
  config: AuthConfig | null;
  token: string | null;       // Google ID token (JWT) when auth_mode=google_oauth
  email: string | null;
  name: string | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  setToken: (jwt: string, decoded: { email: string; name?: string }) => void;
  signOut: () => void;
};

const TOKEN_STORAGE_KEY = 'zen.gis.token';

function decodeJwt(jwt: string): { email?: string; name?: string; exp?: number } {
  try {
    const [, payload] = jwt.split('.');
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json);
  } catch {
    return {};
  }
}

export const useAuth = create<AuthState>((set, get) => ({
  config: null,
  token: typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(TOKEN_STORAGE_KEY) : null,
  email: null,
  name: null,
  loading: false,
  error: null,

  async load() {
    if (get().loading || get().config) return;
    set({ loading: true, error: null });
    try {
      const res = await fetch('/api/auth/config');
      if (!res.ok) throw new Error(`/api/auth/config → ${res.status}`);
      const config = (await res.json()) as AuthConfig;

      // If we restored a token from sessionStorage, re-hydrate user fields.
      const existing = get().token;
      if (existing) {
        const decoded = decodeJwt(existing);
        if (decoded.exp && decoded.exp * 1000 < Date.now()) {
          // expired
          sessionStorage.removeItem(TOKEN_STORAGE_KEY);
          set({ token: null, email: null, name: null, config, loading: false });
        } else {
          set({
            config,
            email: decoded.email ?? null,
            name: decoded.name ?? null,
            loading: false,
          });
        }
        return;
      }
      set({ config, loading: false });
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  },

  setToken(jwt, decoded) {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, jwt);
    set({ token: jwt, email: decoded.email, name: decoded.name ?? null });
  },

  signOut() {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    set({ token: null, email: null, name: null });
    // Also invalidate the active GIS session if the script is loaded.
    const w = window as Window & {
      google?: { accounts?: { id?: { disableAutoSelect?: () => void } } };
    };
    w.google?.accounts?.id?.disableAutoSelect?.();
  },
}));

/** Read the current ID token. Returns null when no auth_mode=google_oauth
 * session exists; callers fall back to the dev token. */
export function currentToken(): string | null {
  return useAuth.getState().token;
}

/** Returns true when google_oauth is the configured mode AND we don't
 * have a token yet. The SPA shows the sign-in gate when this is true. */
export function needsGoogleSignIn(): boolean {
  const { config, token } = useAuth.getState();
  return !!config && config.auth_mode === 'google_oauth' && !token;
}

/** Decode the GIS ID token returned by `google.accounts.id.initialize`. */
export function decodeIdToken(jwt: string): { email?: string; name?: string } {
  return decodeJwt(jwt);
}
