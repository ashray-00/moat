"use client";

import { useEffect, useState } from "react";
import {
  type AdminIngestJob,
  type BillingMe,
  type OrgMe,
  acceptOrgInvite,
  adminReingest,
  fetchAdminJobs,
  fetchAdminMe,
  fetchBillingMe,
  fetchOrgMe,
  inviteOrgMember,
  openBillingPortal,
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
  const [org, setOrg] = useState<OrgMe | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminJobs, setAdminJobs] = useState<AdminIngestJob[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteId, setInviteId] = useState("");
  const [lastInviteId, setLastInviteId] = useState<string | null>(null);
  const [reingestTicker, setReingestTicker] = useState("");

  async function reload() {
    const [billing, orgMe, admin] = await Promise.all([
      fetchBillingMe(accessToken),
      fetchOrgMe(accessToken).catch(() => null),
      fetchAdminMe(accessToken),
    ]);
    setMe(billing);
    if (orgMe) setOrg(orgMe);
    setIsAdmin(admin.admin);
    if (admin.admin) {
      const jobs = await fetchAdminJobs(accessToken).catch(() => ({ jobs: [] }));
      setAdminJobs(jobs.jobs ?? []);
    }
  }

  useEffect(() => {
    let cancelled = false;
    reload()
      .catch((e) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Could not load usage");
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const usedPct =
    me && me.limit > 0 ? Math.min(100, Math.round((me.used / me.limit) * 100)) : 0;

  async function onUpgrade(plan: "pro" | "team") {
    setActionError(null);
    setBusyPlan(plan);
    try {
      const { url } = await startCheckout(accessToken, plan);
      window.location.assign(url);
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Checkout unavailable right now.",
      );
      setBusyPlan(null);
    }
  }

  async function onManageBilling() {
    setActionError(null);
    setBusyPlan("portal");
    try {
      const { url } = await openBillingPortal(accessToken);
      window.location.assign(url);
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Billing portal unavailable.",
      );
      setBusyPlan(null);
    }
  }

  async function onInvite() {
    setActionError(null);
    setBusyPlan("invite");
    try {
      const inv = await inviteOrgMember(accessToken, inviteEmail.trim());
      setLastInviteId(inv.invite_id);
      setInviteEmail("");
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Invite failed.");
    } finally {
      setBusyPlan(null);
    }
  }

  async function onAccept() {
    setActionError(null);
    setBusyPlan("accept");
    try {
      await acceptOrgInvite(accessToken, inviteId.trim());
      setInviteId("");
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Accept failed.");
    } finally {
      setBusyPlan(null);
    }
  }

  async function onReingest() {
    setActionError(null);
    setBusyPlan("reingest");
    try {
      await adminReingest(accessToken, reingestTicker.trim());
      setReingestTicker("");
      const jobs = await fetchAdminJobs(accessToken);
      setAdminJobs(jobs.jobs ?? []);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Reingest failed.");
    } finally {
      setBusyPlan(null);
    }
  }

  const canInvite = Boolean(
    org?.org && org.plan === "team" && org.org.role === "owner",
  );

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
            {typeof me.universe_add_limit === "number" && (
              <p className="text-xs text-mist">
                Custom tickers · {me.universe_adds_used ?? 0} of{" "}
                {me.universe_add_limit}
                {me.universe_add_limit === 0
                  ? " (Pro/Team can add coverage)"
                  : ""}
              </p>
            )}
            {me.has_stripe_customer && (
              <button
                type="button"
                disabled={busyPlan !== null}
                onClick={() => void onManageBilling()}
                className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
              >
                {busyPlan === "portal" ? "Opening…" : "Manage billing"}
              </button>
            )}
          </section>
        )}

        <section className="mt-8 space-y-3">
          <h3 className="footnote-label">Team</h3>
          {org?.org ? (
            <div className="space-y-2 text-sm text-ink">
              <p>
                {org.org.name} · {org.member_count}/{org.seat_limit} seats
                {org.pending_invites
                  ? ` · ${org.pending_invites} pending`
                  : ""}
              </p>
              <ul className="space-y-1 text-xs text-mist">
                {org.members.map((m) => (
                  <li key={m.user_id} className="font-mono">
                    {m.user_id.slice(0, 8)}… · {m.role}
                  </li>
                ))}
              </ul>
              {canInvite && (
                <div className="flex gap-2 pt-1">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="teammate@company.com"
                    className="min-w-0 flex-1 rounded-chip border border-line bg-canvas px-2 py-1.5 text-xs text-ink"
                  />
                  <button
                    type="button"
                    disabled={busyPlan !== null || !inviteEmail.trim()}
                    onClick={() => void onInvite()}
                    className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
                  >
                    {busyPlan === "invite" ? "…" : "Invite"}
                  </button>
                </div>
              )}
              {lastInviteId && (
                <p className="break-all font-mono text-[11px] text-stone">
                  Invite id (share privately): {lastInviteId}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-mist">
              No team yet. Upgrade to Team, then invite seats here.
            </p>
          )}
          <div className="flex gap-2">
            <input
              type="text"
              value={inviteId}
              onChange={(e) => setInviteId(e.target.value)}
              placeholder="Paste invite id to join"
              className="min-w-0 flex-1 rounded-chip border border-line bg-canvas px-2 py-1.5 text-xs text-ink"
            />
            <button
              type="button"
              disabled={busyPlan !== null || !inviteId.trim()}
              onClick={() => void onAccept()}
              className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
            >
              {busyPlan === "accept" ? "…" : "Accept"}
            </button>
          </div>
        </section>

        {isAdmin && (
          <section className="mt-8 space-y-3">
            <h3 className="footnote-label">Admin</h3>
            <div className="flex gap-2">
              <input
                type="text"
                value={reingestTicker}
                onChange={(e) => setReingestTicker(e.target.value.toUpperCase())}
                placeholder="TICKER"
                className="min-w-0 flex-1 rounded-chip border border-line bg-canvas px-2 py-1.5 font-mono text-xs text-ink"
              />
              <button
                type="button"
                disabled={busyPlan !== null || !reingestTicker.trim()}
                onClick={() => void onReingest()}
                className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
              >
                {busyPlan === "reingest" ? "…" : "Reingest"}
              </button>
            </div>
            <ul className="max-h-32 space-y-1 overflow-y-auto text-xs text-mist">
              {adminJobs.slice(0, 12).map((j) => (
                <li key={j.id} className="font-mono">
                  {j.ticker} · {j.status}
                  {j.error ? ` · ${j.error.slice(0, 40)}` : ""}
                </li>
              ))}
              {adminJobs.length === 0 && <li>No recent ingest jobs.</li>}
            </ul>
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
                    {typeof p.universe_add_limit === "number"
                      ? ` · +${p.universe_add_limit} custom tickers`
                      : ""}
                    {typeof p.seat_limit === "number" && p.seat_limit > 1
                      ? ` · ${p.seat_limit} seats`
                      : ""}
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
