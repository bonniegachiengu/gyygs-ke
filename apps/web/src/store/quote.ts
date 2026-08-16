/**
 * The customer's draft basket.
 *
 * Derived values (the estimate, whether Continue is enabled) are computed by
 * selectors rather than stored, so QUOTE_CALCULATOR_SPEC §9's "Edit after seeing
 * total -> recalculates live" comes for free and no stale total is possible.
 *
 * Persisted to sessionStorage: a dropped connection or an accidental reload on a
 * mid-range Android must not lose the basket.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { components } from "../lib/api/schema";
import type { DraftAddon, DraftItem } from "../lib/pricing/estimate";

export type QuoteResponse = components["schemas"]["QuoteResponse"];

export const STEPS = [
  "landing",
  "services",
  "configure",
  "quote",
  "where",
  "details",
  "send",
] as const;
export type Step = (typeof STEPS)[number] | "sitevisit";

/** Services that cannot be given an instant price — SPEC §5.7. */
export const VISIT_SERVICES = new Set(["commercial", "post_construction", "other"]);

export type DraftItemWithId = DraftItem & { uid: string };

type SiteVisit = components["schemas"]["SiteVisitDetails"];

export type QuoteState = {
  step: Step;
  items: DraftItemWithId[];
  addons: Record<string, number>;

  area: string | null;
  estate: string;
  day: string | null;
  window: "morning" | "afternoon" | null;

  name: string;
  phone: string;
  recurring: boolean;
  needsTaxInvoice: boolean;
  businessName: string;
  kraPin: string;
  siteVisit: SiteVisit;

  server: QuoteResponse | null;
  submitting: boolean;
  sent: boolean;

  setStep: (step: Step) => void;
  toggleService: (service: string) => void;
  updateItem: (uid: string, patch: Partial<DraftItem>) => void;
  removeItem: (uid: string) => void;
  setAddonQty: (key: string, qty: number) => void;
  set: (patch: Partial<QuoteState>) => void;
  reset: () => void;
};

let seq = 0;
const uid = () => `i${++seq}${Date.now().toString(36)}`;

const BLANK = {
  step: "landing" as Step,
  items: [] as DraftItemWithId[],
  addons: {} as Record<string, number>,
  area: null,
  estate: "",
  day: null,
  window: null,
  name: "",
  phone: "",
  recurring: false,
  needsTaxInvoice: false,
  businessName: "",
  kraPin: "",
  siteVisit: {} as SiteVisit,
  server: null,
  submitting: false,
  sent: false,
};

export const useQuote = create<QuoteState>()(
  persist(
    (set) => ({
      ...BLANK,

      setStep: (step) => set({ step }),

      toggleService: (service) =>
        set((s) => {
          const existing = s.items.filter((i) => i.service === service);
          if (existing.length) {
            return { items: s.items.filter((i) => i.service !== service) };
          }
          return { items: [...s.items, { uid: uid(), service, qty: 1 }] };
        }),

      updateItem: (id, patch) =>
        set((s) => ({
          items: s.items.map((i) => (i.uid === id ? { ...i, ...patch } : i)),
        })),

      removeItem: (id) => set((s) => ({ items: s.items.filter((i) => i.uid !== id) })),

      setAddonQty: (key, qty) =>
        set((s) => {
          const next = { ...s.addons };
          if (qty <= 0) delete next[key];
          else next[key] = qty;
          return { addons: next };
        }),

      set: (patch) => set(patch),
      reset: () => set({ ...BLANK }),
    }),
    {
      name: "myra.quote.v1",
      storage: createJSONStorage(() => sessionStorage),
      // The server response and in-flight flags are per-attempt, not per-basket.
      partialize: ({ server: _s, submitting: _b, sent: _t, ...rest }) => rest,
    },
  ),
);

// ──────────────────────────── derivation helpers ────────────────────────────
//
// These are plain functions, NOT selectors passed to useQuote(). zustand v5 is
// built on useSyncExternalStore, which requires a referentially stable snapshot:
// a selector that builds a fresh array or Set on every call returns a new
// identity each time and React re-renders forever ("Maximum update depth
// exceeded"). Components select the raw slice and wrap these in useMemo.

export const toDraftItems = (items: DraftItemWithId[]): DraftItem[] =>
  items.map(({ uid: _uid, ...item }) => item);

export const toDraftAddons = (addons: Record<string, number>): DraftAddon[] =>
  Object.entries(addons).map(([key, qty]) => ({ key, qty }));

export const toChosenServices = (items: DraftItemWithId[]): Set<string> =>
  new Set(items.map((i) => i.service));

/** Safe as a selector — a boolean is compared by value, not identity. */
export const needsSiteVisit = (s: QuoteState): boolean =>
  s.items.some((i) => VISIT_SERVICES.has(i.service));
