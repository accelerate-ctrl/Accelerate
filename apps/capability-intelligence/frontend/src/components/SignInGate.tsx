// Renders a Google-branded sign-in gate when the backend reports
// AUTH_MODE = google_oauth and the user doesn't yet hold an ID token.
//
// In dev mode (or when google_oauth is configured but the user is
// signed in), this component returns null and the app shell renders
// normally.

import { useEffect, useRef } from 'react';
import iconTeal from '@/assets/zennify/icon_teal.png';
import { decodeIdToken, useAuth } from '@/lib/auth';

// `google.accounts.id` is loaded from https://accounts.google.com/gsi/client
// in index.html. We type-shim the global without pulling a full @types pkg.
declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (opts: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            opts: {
              type?: 'standard' | 'icon';
              theme?: 'outline' | 'filled_blue' | 'filled_black';
              size?: 'small' | 'medium' | 'large';
              text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
              shape?: 'rectangular' | 'pill' | 'circle' | 'square';
              logo_alignment?: 'left' | 'center';
              width?: number;
            },
          ) => void;
          prompt: () => void;
          disableAutoSelect?: () => void;
        };
      };
    };
  }
}

export default function SignInGate() {
  const { config, token, setToken } = useAuth();
  const buttonRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!config || config.auth_mode !== 'google_oauth' || token) return;
    if (!config.google_oauth_client_id) return;

    // Wait for the GIS script to load (deferred in index.html).
    let cancelled = false;
    const tryInit = () => {
      if (cancelled) return;
      const gid = window.google?.accounts?.id;
      if (!gid || !buttonRef.current) {
        setTimeout(tryInit, 100);
        return;
      }
      gid.initialize({
        client_id: config.google_oauth_client_id!,
        callback: (response) => {
          if (!response.credential) return;
          const decoded = decodeIdToken(response.credential);
          setToken(response.credential, {
            email: decoded.email ?? '',
            name: decoded.name,
          });
        },
        auto_select: false,
        cancel_on_tap_outside: false,
      });
      gid.renderButton(buttonRef.current, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'pill',
        logo_alignment: 'left',
        width: 280,
      });
    };
    tryInit();

    return () => {
      cancelled = true;
    };
  }, [config, token, setToken]);

  if (!config) return null;
  if (config.auth_mode !== 'google_oauth') return null;
  if (token) return null;

  return (
    <div className="fixed inset-0 z-50 bg-zen-ice flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg border border-zen-separator p-8 text-center">
        <img src={iconTeal} alt="Zennify" className="w-16 h-16 mx-auto mb-4" />
        <h1 className="text-xl font-semibold text-zen-dark-green">Zennify Capability Intelligence</h1>
        <p className="text-sm text-zen-text-gray mt-2">
          Sign in with your <span className="font-medium text-zen-dark-teal">
            @{config.allowed_domain}
          </span>{' '}
          Google account to continue.
        </p>
        <div ref={buttonRef} className="mt-6 flex justify-center" />
        {!config.google_oauth_client_id && (
          <div className="mt-4 text-[11px] text-zen-orange">
            GOOGLE_OAUTH_CLIENT_ID is not configured for this revision.
          </div>
        )}
        <div className="mt-6 text-[10px] text-zen-muted-text">
          Powered by Google Identity Services
        </div>
      </div>
    </div>
  );
}
