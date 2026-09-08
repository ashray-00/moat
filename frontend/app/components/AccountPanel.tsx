"use client";

import { useEffect, useState } from "react";
import {
  type BillingMe,
  fetchBillingMe,
  startCheckout,
} from "../lib/ask";
import { signOut } from "../lib/auth";

type AccountPanelProps = {
  accessToken: string;
  displayName: string;
  email?: string | null;
  onClose: () => void;
};

export function AccountPanel({
  accessToken,
  displayName,
  email,
  onClose,
}: AccountPanelProps) {
  const [me, setMe] = useState<BillingMe | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchBillingMe(accessToken)
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Could not load usage");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const usedPct =
    me && me.limit > 0 ? Math.min(100, Math.round((me.used / me.limit) * 100)) : 0;

  async function onUpgrade(plan: "pro" | "team") {
    setActionError(null);
    setBusyPlan(plan);
    try {
      const { url } = await startCheckout(accessToken, plan);
      // Full-page redirect to Stripe Checkout Hosted page.
      window.location.assign(url);
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Checkout unavailable right now.",
      );
      setBusyPlan(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center bg-ink/25 px-4 py-10 backdrop-blur-[1px] sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="account-title"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-search border border-line bg-canvas p-5 shadow-search sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              id="account-title"
              className="font-display text-2xl font-medium tracking-tight text-ink"
            >
              Account
            </h2>
            <p className="mt-1 text-sm text-mist">
              <span className="text-ink">{displayName}</span>
              {email ? <span className="text-stone"> · {email}</span> : null}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-chip border border-line px-2.5 py-1 text-xs text-mist hover:border-accent hover:text-ink"
          >
            Close
          </button>
        </div>

        {loadError && (
          <p className="mt-4 rounded-search border border-line bg-surface px-3 py-2 text-sm text-ink">
            {loadError}
          </p>
        )}

        {me && (
          <section className="mt-6 space-y-3">
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-sm text-ink">{me.label} plan</p>
              <p className="font-mono text-xs text-stone">
                {me.used} / {me.limit} this month
              </p>
            </div>
            <div
              className="h-1.5 overflow-hidden rounded-full bg-line"
              aria-hidden
            >
              <div
                className="h-full bg-accent transition-[width] duration-300"
                style={{ width: `${usedPct}%` }}
              />
            </div>
            <p className="text-xs text-mist">
              {me.remaining} asks remaining · up to {me.rpm} requests / minute
            </p>
          </section>
        )}

        <section className="mt-8 space-y-3">
          <h3 className="footnote-label">Plans</h3>
          <div className="space-y-2">
            {(me?.plans ?? []).map((p) => (
              <div
                key={p.id}
                className={[
                  "flex flex-col gap-2 rounded-search border px-3 py-3 sm:flex-row sm:items-center sm:justify-between",
                  p.current ? "border-accent bg-surface" : "border-line bg-canvas",
                ].join(" ")}
              >
                <div>
                  <p className="text-sm text-ink">
                    {p.label}
                    {p.current ? (
                      <span className="ml-2 text-xs text-mist">Current</span>
                    ) : null}
                  </p>
                  <p className="mt-0.5 text-xs text-mist">
                    {p.monthly_asks.toLocaleString()} asks / month · {p.rpm}{" "}
                    req/min
                  </p>
                </div>
                {p.checkout && !p.current && (
                  <button
                    type="button"
                    disabled={busyPlan !== null}
                    onClick={() => {
                      if (!p.checkout_ready) {
                        setActionError(
                          "Billing is not configured yet for this plan. Set Stripe price IDs on the API.",
                        );
                        return;
                      }
                      void onUpgrade(p.id as "pro" | "team");
                    }}
                    className="shrink-0 rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
                  >
                    {busyPlan === p.id
                      ? "Redirecting…"
                      : p.checkout_ready
                        ? `Upgrade to ${p.label}`
                        : "Unavailable"}
                  </button>
                )}
              </div>
            ))}
          </div>
          {actionError && (
            <p className="text-sm text-ink" role="alert">
              {actionError}
            </p>
          )}
          {me && !me.stripe_checkout_available && (
            <p className="text-xs text-stone">
              Checkout opens once Stripe keys and Pro/Team price IDs are set on
              the API. Limits still apply to your current plan.
            </p>
          )}
        </section>

        <div className="mt-8 flex justify-end border-t border-line pt-4">
          <button
            type="button"
            onClick={() => signOut()}
            className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
