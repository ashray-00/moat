"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../lib/supabase";

/**
 * Completes the magic-link / PKCE handshake, then returns home.
 * Session is stored by the Supabase client in this browser only.
 */
export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    async function finish() {
      if (!supabase) {
        router.replace("/");
        return;
      }
      const url = new URL(window.location.href);
      const code = url.searchParams.get("code");
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          console.error("auth callback", error.message);
        }
      } else {
        // Hash-based tokens (implicit) are picked up by getSession on the client.
        await supabase.auth.getSession();
      }
      if (!cancelled) router.replace("/");
    }

    void finish();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main className="flex min-h-full items-center justify-center px-5">
      <p className="text-sm text-mist">Signing you in…</p>
    </main>
  );
}
