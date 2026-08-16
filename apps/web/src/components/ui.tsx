/**
 * UI primitives.
 *
 * Every interactive element carries `min-h-12` (Tailwind 12 = 3rem = 48px) —
 * QUOTE_CALCULATOR_SPEC §11 requires large tap targets, and putting it in the
 * base classes means it cannot be forgotten on a new screen.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

import { ksh } from "../lib/format";

const TAP = "min-h-12 min-w-12";

// ──────────────────────────────── button ────────────────────────────────

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  full?: boolean;
};

const VARIANTS = {
  primary: "bg-green text-white hover:bg-green-deep active:bg-green-deep shadow-sm",
  secondary: "bg-white text-navy ring-1 ring-navy/20 hover:bg-mist",
  ghost: "bg-transparent text-navy hover:bg-navy/5",
} as const;

export function Button({ variant = "primary", full, className = "", ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={[
        TAP,
        "inline-flex items-center justify-center gap-2 rounded-xl px-5 text-base font-semibold",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        VARIANTS[variant],
        full ? "w-full" : "",
        className,
      ].join(" ")}
    />
  );
}

// ───────────────────────────────── layout ─────────────────────────────────

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-[var(--radius-card)] bg-white p-4 shadow-sm ring-1 ring-navy/10 ${className}`}
    >
      {children}
    </section>
  );
}

export function Screen({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4 pb-28">{children}</div>;
}

export function Heading({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header>
      <h1 className="text-2xl font-bold text-navy">{children}</h1>
      {sub && <p className="mt-1 text-sm text-ink/60">{sub}</p>}
    </header>
  );
}

/** Pinned action bar — the one clear action per step (§11). */
export function ActionBar({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 border-t border-navy/10 bg-white/95 p-4 backdrop-blur">
      <div className="mx-auto flex max-w-md flex-col gap-2">{children}</div>
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div
      className="h-1 w-full bg-navy/10"
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full bg-green transition-[width] duration-300"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  );
}

// ───────────────────────────────── inputs ─────────────────────────────────

export function Chip({
  selected,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button
      {...rest}
      aria-pressed={selected}
      className={[
        TAP,
        "rounded-full px-4 text-sm font-medium transition-colors",
        selected
          ? "bg-navy text-white"
          : "bg-white text-navy ring-1 ring-navy/20 hover:bg-mist",
        className,
      ].join(" ")}
    />
  );
}

export function SelectCard({
  selected,
  icon,
  title,
  hint,
  onClick,
}: {
  selected: boolean;
  icon?: string | null;
  title: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={[
        "flex min-h-16 w-full items-center gap-3 rounded-[var(--radius-card)] p-4 text-left",
        "transition-colors",
        selected
          ? "bg-white ring-2 ring-green"
          : "bg-white ring-1 ring-navy/10 hover:ring-navy/25",
      ].join(" ")}
    >
      {icon && (
        <span className="text-2xl" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="flex-1">
        <span className="block font-semibold text-navy">{title}</span>
        {hint && <span className="block text-sm text-ink/60">{hint}</span>}
      </span>
      <span
        aria-hidden="true"
        className={[
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sm text-white",
          selected ? "bg-green" : "bg-navy/10",
        ].join(" ")}
      >
        {selected ? "✓" : ""}
      </span>
    </button>
  );
}

export function Counter({
  value,
  min = 0,
  max = 99,
  onChange,
  label,
}: {
  value: number;
  min?: number;
  max?: number;
  onChange: (next: number) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        className={`${TAP} rounded-full bg-white text-xl font-bold text-navy ring-1 ring-navy/20 disabled:opacity-30`}
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
        aria-label={`decrease ${label}`}
      >
        −
      </button>
      <span className="w-8 text-center text-lg font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className={`${TAP} rounded-full bg-white text-xl font-bold text-navy ring-1 ring-navy/20 disabled:opacity-30`}
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
        aria-label={`increase ${label}`}
      >
        +
      </button>
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-navy">{label}</span>
      <input
        {...rest}
        className={[
          TAP,
          "mt-1 w-full rounded-xl bg-white px-4 text-base text-ink",
          "ring-1 outline-none focus:ring-2",
          error ? "ring-red-500 focus:ring-red-500" : "ring-navy/20 focus:ring-green",
        ].join(" ")}
      />
      {(error || hint) && (
        <span className={`mt-1 block text-sm ${error ? "text-red-700" : "text-ink/55"}`}>
          {error || hint}
        </span>
      )}
    </label>
  );
}

// ──────────────────────────────── feedback ────────────────────────────────

export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warn" | "error";
}) {
  const tones = {
    info: "bg-navy/5 text-navy",
    warn: "bg-amber-50 text-amber-900 ring-1 ring-amber-200",
    error: "bg-red-50 text-red-800 ring-1 ring-red-200",
  } as const;
  return <p className={`rounded-xl px-4 py-3 text-sm ${tones[tone]}`}>{children}</p>;
}

/** "Best on a quick site visit" — QUOTE_CALCULATOR_SPEC §5 Step 2. */
export function VisitBadge() {
  return (
    <span className="mt-0.5 block text-xs font-medium text-amber-700">
      Best on a quick site visit
    </span>
  );
}

export function Money({ amount, from = false }: { amount: number; from?: boolean }) {
  return (
    <span className="font-semibold tabular-nums text-navy">
      {from ? `from ${ksh(amount)}` : ksh(amount)}
    </span>
  );
}
