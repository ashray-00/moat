"use client";

import { useState } from "react";
import { AuthScreen } from "./components/AuthScreen";
import { ResearchWorkspace } from "./components/ResearchWorkspace";
import { ThemeToggle } from "./components/ThemeToggle";
import { useAuthSession } from "./lib/auth";

function ConfigMissing() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-16">
      <p className="font-display text-3xl font-medium tracking-tight text-ink">
        Moat
      </p>
      <p className="mt-4 text-sm leading-relaxed text-mist">
        Authentication is not configured. Set{" "}
        <span className="font-mono text-xs text-ink">
          NEXT_PUBLIC_SUPABASE_URL
        </span>{" "}
        and{" "}
        <span className="font-mono text-xs text-ink">
          NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
        </span>{" "}
        in the frontend environment, then restart the app.
      </p>
    </div>
  );
}

export default function Home() {
  const { session, ready, authConfigured, displayName, signedIn, user } =
    useAuthSession();
  const [authError, setAuthError] = useState<string | null>(null);

  if (!ready) {
    return (
      <div className="flex min-h-full flex-1 items-center justify-center">
        <p className="text-sm text-mist">Loading…</p>
      </div>
    );
  }

  if (!authConfigured) {
    return (
      <div className="flex min-h-full flex-col">
        <header className="border-b border-line/80">
          <div className="mx-auto flex max-w-measure items-center justify-end px-5 py-4 sm:px-6">
            <ThemeToggle />
          </div>
        </header>
        <ConfigMissing />
      </div>
    );
  }

  if (!signedIn || !session?.access_token || !user) {
    return (
      <div className="flex min-h-full flex-col">
        <header className="border-b border-line/80">
          <div className="mx-auto flex max-w-measure items-center justify-end px-5 py-4 sm:px-6">
            <ThemeToggle />
          </div>
        </header>
        <AuthScreen onError={setAuthError} />
        {authError && (
          <div
            role="alert"
            className="mx-auto w-full max-w-md px-5 pb-10 text-sm text-ink"
          >
            <div className="rounded-search border border-line bg-surface px-4 py-3">
              {authError}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <ResearchWorkspace
      key={user.id}
      accessToken={session.access_token}
      displayName={displayName}
      user={user}
    />
  );
}
