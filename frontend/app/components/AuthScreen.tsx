"use client";

import { FormEvent, useState } from "react";
import { MagicLinkMode, sendMagicLink } from "../lib/auth";

type AuthScreenProps = {
  onError: (message: string | null) => void;
};

export function AuthScreen({ onError }: AuthScreenProps) {
  const [mode, setMode] = useState<MagicLinkMode>("signin");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    onError(null);
    setBusy(true);
    try {
      const err = await sendMagicLink(email, {
        mode,
        fullName: mode === "signup" ? fullName : undefined,
      });
      if (err) {
        onError(err);
        setSentTo(null);
      } else {
        setSentTo(email.trim().toLowerCase());
      }
    } finally {
      setBusy(false);
    }
  }

  if (sentTo) {
    return (
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-16 sm:px-6">
        <p className="font-display text-3xl font-medium tracking-tight text-ink">
          Check your email
        </p>
        <p className="mt-3 text-[0.95rem] leading-relaxed text-mist">
          We sent a sign-in link to{" "}
          <span className="text-ink">{sentTo}</span>. Open it on this device
          to continue. The link is only for you — it creates a session in this
          browser after you click it.
        </p>
        <button
          type="button"
          className="mt-8 self-start text-sm text-mist underline-offset-2 hover:text-ink hover:underline"
          onClick={() => {
            setSentTo(null);
            onError(null);
          }}
        >
          Use a different email
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-5 py-16 sm:px-6">
      <p className="font-display text-3xl font-medium tracking-tight text-ink">
        Moat
      </p>
      <p className="mt-2 text-sm text-mist">
        Equity research over SEC filings
      </p>

      <div className="mt-10 flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => {
            setMode("signin");
            onError(null);
          }}
          className={`rounded-chip border px-3 py-1.5 ${
            mode === "signin"
              ? "border-accent text-ink"
              : "border-line text-mist"
          }`}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("signup");
            onError(null);
          }}
          className={`rounded-chip border px-3 py-1.5 ${
            mode === "signup"
              ? "border-accent text-ink"
              : "border-line text-mist"
          }`}
        >
          Create account
        </button>
      </div>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {mode === "signup" && (
          <div className="space-y-1.5">
            <label htmlFor="full-name" className="text-xs text-mist">
              Full name
            </label>
            <input
              id="full-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
              className="w-full rounded-search border border-line bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
              placeholder="Ada Lovelace"
            />
          </div>
        )}
        <div className="space-y-1.5">
          <label htmlFor="email" className="text-xs text-mist">
            Work email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            className="w-full rounded-search border border-line bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            placeholder="you@firm.com"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="flex w-full items-center justify-center rounded-search bg-accent px-4 py-2.5 text-sm font-medium text-canvas transition-colors hover:bg-accent-hover disabled:opacity-45"
        >
          {busy
            ? "Sending link…"
            : mode === "signup"
              ? "Create account"
              : "Email me a sign-in link"}
        </button>
      </form>

      <p className="mt-6 text-xs leading-relaxed text-stone">
        Passwordless access. No password to remember — we email a one-time
        link. Sessions stay on this device until you sign out.
      </p>
    </div>
  );
}
