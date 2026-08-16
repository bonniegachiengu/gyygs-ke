/**
 * Client-side estimator — a direct port of `apps/api/app/domain/pricing.py`.
 *
 * Why this exists: QUOTE_CALCULATOR_SPEC §9 requires the price to move the instant
 * a customer taps, on slow mobile data, before any round trip. The server total
 * is still the quote of record (§6) — this only drives the live display.
 *
 * NO PRICE IS HARDCODED HERE. Everything is read from the catalogue returned by
 * GET /api/pricing, so PRICES.md stays the single source of truth. The same
 * ordered algorithm, the same integer arithmetic and the same label grammar are
 * used, so the estimate and the server's lines are identical strings.
 */

import type { components } from "../api/schema";

type Catalogue = components["schemas"]["PricingCatalogue"];
type Service = components["schemas"]["Service"];
type Addon = components["schemas"]["Addon"];
export type DraftItem = components["schemas"]["QuoteItem"];
export type DraftAddon = components["schemas"]["QuoteAddon"];

export type EstimateLine = { label: string; amount: number; visit: boolean };

export type Estimate = {
  lines: EstimateLine[];
  subtotal: number;
  discount: number;
  total: number;
  visitFirst: boolean;
  minimumApplied: boolean;
  minimumAdjustment: number;
};

const SEP = " — "; // em dash, matches SPEC §3 / §7
const qtySuffix = (qty: number) => (qty > 1 ? ` ×${qty}` : "");
const money = (n: number) => n.toLocaleString("en-US");

export const EMPTY_ESTIMATE: Estimate = {
  lines: [],
  subtotal: 0,
  discount: 0,
  total: 0,
  visitFirst: false,
  minimumApplied: false,
  minimumAdjustment: 0,
};

// ───────────────────────────── item strategies ─────────────────────────────

function perUnit(item: DraftItem, svc: Service): EstimateLine[] {
  const rate = svc.rate ?? 0;
  const floor = svc.min_units ?? 1;
  const units = Math.max(item.seats ?? floor, floor);
  const qty = item.qty ?? 1;

  // Singular matters now that a single seat is quotable (no 2-seat floor).
  const unitWord = units === 1 ? svc.unit : `${svc.unit}s`;
  const lines: EstimateLine[] = [
    {
      label: `${svc.label}${SEP}${units} ${unitWord}${qtySuffix(qty)}`,
      amount: rate * units * qty,
      visit: false,
    },
  ];

  for (const extra of item.extras ?? []) {
    const def = (svc.extras ?? []).find((e) => e.key === extra.key);
    if (!def) continue;
    const eq = extra.qty ?? 1;
    lines.push({
      label: `Add-on${SEP}${def.label}${qtySuffix(eq)}`,
      amount: def.price * eq,
      visit: false,
    });
  }
  return lines;
}

function tiered(item: DraftItem, svc: Service): EstimateLine[] {
  const tier = (svc.tiers ?? []).find((t) => t.key === item.tier);
  if (!tier) return [];
  const qty = item.qty ?? 1;

  const lines: EstimateLine[] = [
    {
      label: `${svc.label}${SEP}${tier.label}${qtySuffix(qty)}`,
      amount: tier.price * qty,
      visit: false,
    },
  ];

  const extraBedrooms = item.extra_bedrooms ?? 0;
  if (extraBedrooms > 0 && svc.extra) {
    lines.push({
      label: `${svc.extra.label}${qtySuffix(extraBedrooms)}`,
      amount: svc.extra.price * extraBedrooms,
      visit: false,
    });
  }
  return lines;
}

function sizeTiered(item: DraftItem, svc: Service): EstimateLine[] {
  const tiers = svc.tiers ?? [];
  let base = 0;
  let visit = false;
  let core: string;
  let suffix = "";

  if (svc.larger === "visit" && item.size === "larger") {
    core = `${svc.label}${SEP}larger than ${tiers[tiers.length - 1]?.label ?? ""}`;
    suffix = " (on site visit)";
    visit = true;
  } else if (svc.above && item.size === svc.above.key) {
    base = svc.above.price;
    core = `${svc.label}${SEP}${svc.above.label}`;
    suffix = " (from)";
    visit = svc.above.from ?? true; // AboveDef.from defaults to true server-side
  } else {
    const tier = tiers.find((t) => t.key === item.size);
    if (!tier) return [];
    base = tier.price;
    core = `${svc.label}${SEP}${tier.label}`;
  }

  // Modifiers are ADDITIVE — see the Python engine's note on why, and why the
  // test asserts on a 6×9 carpet rather than a 5×7.
  for (const key of item.modifiers ?? []) {
    const mod = (svc.modifiers ?? []).find((m) => m.key === key);
    if (!mod) continue;
    if (mod.add_range) {
      const lo = mod.add_range[0] ?? 0;
      const hi = mod.add_range[1] ?? lo;
      base += lo; // lower bound only — never quote above what they will pay
      suffix += ` (${mod.label} +${money(lo)}–${money(hi)})`;
      visit = true;
    } else if (mod.add != null) {
      base += mod.add;
      suffix += ` (${mod.label} +${money(mod.add)})`;
    }
  }

  const qty = item.qty ?? 1;
  return [{ label: `${core}${qtySuffix(qty)}${suffix}`, amount: base * qty, visit }];
}

function visitOnly(item: DraftItem, svc: Service): EstimateLine[] {
  const base = svc.from ?? 0;
  const suffix = svc.from ? " (from)" : " (on site visit)";
  const note = item.note?.trim();
  const label = note ? `${svc.label}${SEP}${note}${suffix}` : `${svc.label}${suffix}`;
  return [{ label, amount: base * (item.qty ?? 1), visit: true }];
}

export function priceItem(item: DraftItem, cat: Catalogue): EstimateLine[] {
  const svc = cat.services.find((s) => s.key === item.service);
  if (!svc) return [];
  switch (svc.strategy) {
    case "per_unit":
      return perUnit(item, svc);
    case "tier":
      return tiered(item, svc);
    case "size_tier":
      return sizeTiered(item, svc);
    case "visit":
      return visitOnly(item, svc);
    default:
      return [];
  }
}

export function priceAddon(addon: DraftAddon, cat: Catalogue): EstimateLine | null {
  const def: Addon | undefined = cat.addons.find((a) => a.key === addon.key);
  if (!def) return null;
  const qty = addon.qty ?? 1;
  const label = `Add-on${SEP}${def.label}${qtySuffix(qty)}`;

  if (def.price_range) {
    const lo = def.price_range[0] ?? 0;
    const hi = def.price_range[1] ?? lo;
    return { label: `${label} (${money(lo)}–${money(hi)})`, amount: lo * qty, visit: true };
  }
  const price = def.price ?? 0;
  if (def.from) return { label: `${label} (from)`, amount: price * qty, visit: true };
  return { label, amount: price * qty, visit: false };
}

// ──────────────────────────────── assembly ────────────────────────────────

/**
 * `recurring` is intent and never moves the price — it only feeds the
 * recurring_requires_visit rule. `repeatCustomer` is what earns the discount,
 * and nothing in v1 sets it: there is no customer record, so every quote is
 * priced as a first job. Booking (Phase 3) is what will set it.
 */
export function estimate(
  cat: Catalogue | null,
  items: DraftItem[],
  addons: DraftAddon[],
  recurring: boolean,
  repeatCustomer = false,
): Estimate {
  if (!cat) return EMPTY_ESTIMATE;

  const lines: EstimateLine[] = [];
  for (const item of items) lines.push(...priceItem(item, cat));
  for (const addon of addons) {
    const line = priceAddon(addon, cat);
    if (line) lines.push(line);
  }
  if (lines.length === 0) return EMPTY_ESTIMATE;

  const subtotal = lines.reduce((sum, l) => sum + l.amount, 0);
  // Integer floor division, exactly like the server — no fractional shillings.
  const discount = repeatCustomer
    ? Math.floor((subtotal * cat.rules.recurring_discount_pct) / 100)
    : 0;

  const net = subtotal - discount;
  const total = Math.max(net, cat.minimum_callout);
  const minimumApplied = total > net;

  const visitFirst =
    lines.some((l) => l.visit) || Boolean(recurring && cat.rules.recurring_requires_visit);

  return {
    lines,
    subtotal,
    discount,
    total,
    visitFirst,
    minimumApplied,
    minimumAdjustment: total - net,
  };
}
