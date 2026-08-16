/**
 * Makes the Android hardware back button walk back through the stepper instead
 * of leaving the site.
 *
 * ~30 lines instead of react-router-dom (~10 kB gzipped), which this single-page
 * flow does not otherwise need — QUOTE_CALCULATOR_SPEC §5 is explicit that this
 * is "one page that moves through steps (not a multi-page site)".
 */

import { useEffect, useRef } from "react";

import type { Step } from "../store/quote";

export function useStepHistory(step: Step, setStep: (s: Step) => void): void {
  const previous = useRef<Step | null>(null);

  useEffect(() => {
    if (previous.current === null) {
      history.replaceState({ step }, "");
    } else if (previous.current !== step) {
      history.pushState({ step }, "");
    }
    previous.current = step;
  }, [step]);

  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const target = (event.state as { step?: Step } | null)?.step;
      if (target) {
        previous.current = target; // do not push again for a back navigation
        setStep(target);
      }
    };
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, [setStep]);
}
