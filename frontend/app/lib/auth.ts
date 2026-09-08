"use client";

import { useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import {
  authCallbackUrl,
  authConfigured,
  displayNameFromUser,
  supabase,
} from "./supabase";

export function useAuthSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(() => !authConfigured);

  useEffect(() => {
    if (!authConfigured || !supabase) return;

    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session);
        setReady(true);
      }
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const user = session?.user ?? null;
  return {
    session,
    user,
    ready,
    authConfigured,
    displayName: displayNameFromUser(user),
    signedIn: Boolean(session?.access_token),
  };
}

export type MagicLinkMode = "signin" | "signup";

/**
 * Passwordless email link. Signup may attach a display name in user_metadata.
 * Sign-in rejects unknown emails when shouldCreateUser is false.
 */
export async function sendMagicLink(
  email: string,
  opts: { mode: MagicLinkMode; fullName?: string } = { mode: "signin" },
): Promise<string | null> {
  if (!supabase) return "Authentication is not configured.";
  const trimmed = email.trim().toLowerCase();
  if (!trimmed || !trimmed.includes("@")) return "Enter a valid email address.";

  const isSignup = opts.mode === "signup";
  if (isSignup) {
    const name = (opts.fullName ?? "").trim();
    if (name.length < 2) return "Enter your name (at least 2 characters).";
  }

  const { error } = await supabase.auth.signInWithOtp({
    email: trimmed,
    options: {
      emailRedirectTo: authCallbackUrl(),
      shouldCreateUser: isSignup,
      data: isSignup
        ? { full_name: (opts.fullName ?? "").trim() }
        : undefined,
    },
  });
  return error?.message ?? null;
}

export async function signOut(): Promise<void> {
  if (!supabase) return;
  await supabase.auth.signOut();
}

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export function userLabel(user: User | null): string {
  return displayNameFromUser(user);
}
