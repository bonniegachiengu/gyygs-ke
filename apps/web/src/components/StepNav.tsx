/**
 * Back / forward across the stepper.
 *
 * The flow previously had no reverse gear at all: every screen offered exactly
 * one forward action and nothing else, so a customer who reached a screen they
 * could not satisfy was simply stuck (reported live 25 Aug 2026 on "Where &
 * when"). The Android hardware back button walked the steps via
 * useStepHistory, but nothing on screen said so, and desktop and iOS had
 * nothing at all.
 *
 * CONTEXTUAL, not two permanent arrows:
 *   - Back appears on every screen except the first.
 *   - Forward appears only for a step already in `visited` — a customer who
 *     stepped back can return without re-answering, and nobody is ever offered
 *     a jump past a screen they have not filled in.
 *
 * Each destination keeps its own gate, so neither arrow can bypass validation.
 */

import { prevStep, nextStep } from "../lib/flow";
import { needsSiteVisit, useQuote } from "../store/quote";

function Chevron({ dir }: { dir: "left" | "right" }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-5 w-5">
      <path
        d={dir === "left" ? "M12.5 4 7 10l5.5 6" : "M7.5 4 13 10l-5.5 6"}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const TAP =
  "inline-flex min-h-12 items-center gap-1 rounded-xl px-3 text-sm font-semibold " +
  "text-navy transition-colors hover:bg-navy/5 active:bg-navy/10";

export function StepNav() {
  const step = useQuote((s) => s.step);
  const visited = useQuote((s) => s.visited);
  const setStep = useQuote((s) => s.setStep);
  const visitBranch = useQuote(needsSiteVisit);

  const back = prevStep(step, visitBranch);
  const ahead = nextStep(step, visitBranch);
  // Only offer forward to somewhere they have genuinely already been.
  const forward = ahead && visited.includes(ahead) ? ahead : null;

  return (
    <nav aria-label="Quote steps" className="mb-3 flex items-center justify-between gap-2">
      {back ? (
        <button type="button" className={`${TAP} -ml-3`} onClick={() => setStep(back)}>
          <Chevron dir="left" />
          Back
        </button>
      ) : (
        // Holds the row's height so the eyebrow does not jump between screens.
        <span className="min-h-12" />
      )}

      <p className="text-sm font-semibold tracking-widest text-navy/50 uppercase">
        Myrah Cleaning
      </p>

      {forward ? (
        <button
          type="button"
          className={`${TAP} -mr-3`}
          onClick={() => setStep(forward)}
          aria-label="Forward"
        >
          <Chevron dir="right" />
        </button>
      ) : (
        <span className="min-h-12 w-3" />
      )}
    </nav>
  );
}
