/**
 * The step graph, in one place.
 *
 * WHY THIS FILE EXISTS — the bug it was written for:
 *
 * There are TWO routes through the quote, not one. A priced basket goes
 * services -> configure -> quote -> where. A basket containing a site-visit
 * service (office / post-construction / something else) branches at
 * ChooseServices to `sitevisit` and rejoins at `where` — SKIPPING the `quote`
 * screen entirely.
 *
 * `quote` was the only screen that could set `area`, and `where` gated its
 * Continue on `!area`. So every site-visit customer reached "Where & when",
 * filled it in completely, and found Continue permanently dead with no way
 * back — the flow had no reverse gear either. Reported live 25 Aug 2026
 * (estate "Garden City Mall", i.e. a commercial job: the branch exactly).
 *
 * Keeping both routes as declared data means "what comes before/after this
 * screen" is answered the same way for both, instead of each screen hardcoding
 * its own neighbour and the branch being invisible.
 */

import type { Step } from "../store/quote";

/** Basket with an instant price. */
export const PRICED_FLOW: readonly Step[] = [
  "landing",
  "services",
  "configure",
  "quote",
  "where",
  "details",
  "send",
] as const;

/** Basket that needs a site visit — no instant price, so no `quote` screen. */
export const VISIT_FLOW: readonly Step[] = [
  "landing",
  "services",
  "sitevisit",
  "where",
  "details",
  "send",
] as const;

export const flowFor = (visitBranch: boolean): readonly Step[] =>
  visitBranch ? VISIT_FLOW : PRICED_FLOW;

/**
 * The route this step actually lives on.
 *
 * Guards the in-between moment where the two disagree: a customer standing on
 * `sitevisit` who unticks the last visit service flips `visitBranch` to false
 * while still being ON a screen that only exists in the visit route. Falling
 * back to whichever route contains the step keeps Back working instead of
 * returning null and stranding them again — which is the whole class of bug
 * this file exists to end.
 */
function routeFor(step: Step, visitBranch: boolean): readonly Step[] {
  const primary = flowFor(visitBranch);
  if (primary.includes(step)) return primary;
  const other = flowFor(!visitBranch);
  return other.includes(step) ? other : primary;
}

export function prevStep(step: Step, visitBranch: boolean): Step | null {
  const route = routeFor(step, visitBranch);
  const i = route.indexOf(step);
  return i > 0 ? (route[i - 1] as Step) : null;
}

export function nextStep(step: Step, visitBranch: boolean): Step | null {
  const route = routeFor(step, visitBranch);
  const i = route.indexOf(step);
  return i >= 0 && i < route.length - 1 ? (route[i + 1] as Step) : null;
}
