import Link from "next/link";

export default function BillingCancelPage() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-md flex-col justify-center px-5 py-16">
      <p className="font-display text-3xl font-medium tracking-tight text-ink">
        Checkout canceled
      </p>
      <p className="mt-3 text-sm leading-relaxed text-mist">
        No charge was made. You can upgrade anytime from Account.
      </p>
      <Link
        href="/"
        className="mt-8 self-start rounded-search bg-accent px-4 py-2.5 text-sm font-medium text-canvas hover:bg-accent-hover"
      >
        Back to research
      </Link>
    </main>
  );
}
