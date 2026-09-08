import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

/** True when publishable credentials are present (required for the product UI). */
export const authConfigured = Boolean(url && publishableKey);

export const supabase: SupabaseClient | null = authConfigured
  ? createClient(url, publishableKey)
  : null;

export function authCallbackUrl(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/auth/callback`;
}

export { displayNameFromUser } from "./userDisplay";
