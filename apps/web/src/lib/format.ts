/**
 * Number and date formatting.
 *
 * QUOTE_CALCULATOR_SPEC §12: "Numbers formatted with separators (KSh 3,800)."
 */

// en-US rather than en-KE on purpose: comma grouping is then guaranteed on every
// mid-range Android WebView, regardless of which locale data the device shipped.
const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const ksh = (amount: number): string => `KSh ${nf.format(amount)}`;

export const plural = (n: number, one: string, many = `${one}s`): string =>
  `${n} ${n === 1 ? one : many}`;

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** "Sat, morning" — mirrors the server's builder so the recap and the WhatsApp
 *  text never disagree. */
export function formatPreferred(day?: string, window?: string): string | null {
  const parts: string[] = [];
  if (day) {
    const d = new Date(`${day}T00:00:00`);
    if (!Number.isNaN(d.getTime())) parts.push(DOW[(d.getDay() + 6) % 7]!);
  }
  if (window) parts.push(window);
  return parts.length ? parts.join(", ") : null;
}

/** Today / tomorrow / +n as an ISO date, for the quick-pick day buttons. */
export function isoDayOffset(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

/** Accepts 07xx / 01xx / +2547xx and reports whether the server will take it. */
export function isValidKenyanMobile(raw: string): boolean {
  const digits = raw.replace(/[^\d+]/g, "").replace(/^\+/, "");
  const national = digits.startsWith("254")
    ? digits.slice(3)
    : digits.startsWith("0")
      ? digits.slice(1)
      : digits;
  return /^[71]\d{8}$/.test(national);
}
