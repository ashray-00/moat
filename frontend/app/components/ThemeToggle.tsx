"use client";

import { useSyncExternalStore } from "react";

function subscribeTheme(onStoreChange: () => void) {
  const obs = new MutationObserver(onStoreChange);
  obs.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => obs.disconnect();
}

function themeIsDark() {
  return document.documentElement.classList.contains("dark");
}

export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribeTheme, themeIsDark, () => false);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("moat-theme", next ? "dark" : "light");
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-chip border border-line px-2.5 py-1 text-xs text-mist transition-colors hover:border-accent hover:text-ink active:scale-[0.97]"
    >
      {dark ? "Light" : "Dark"}
    </button>
  );
}
