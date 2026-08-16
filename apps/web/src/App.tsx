import { Button, Notice, ProgressBar } from "./components/ui";
import { useCatalogue } from "./lib/useCatalogue";
import { useStepHistory } from "./lib/useStepHistory";
import { ChooseServices } from "./screens/ChooseServices";
import { Configure } from "./screens/Configure";
import { Details } from "./screens/Details";
import { Landing } from "./screens/Landing";
import { QuoteSummary } from "./screens/QuoteSummary";
import { Send } from "./screens/Send";
import { SiteVisit } from "./screens/SiteVisit";
import { WhereWhen } from "./screens/WhereWhen";
import { STEPS, useQuote } from "./store/quote";

/** Progress along the seven steps; the site-visit branch sits alongside Configure. */
function progressFor(step: string): number {
  if (step === "sitevisit") return 2 / (STEPS.length - 1);
  const i = STEPS.indexOf(step as (typeof STEPS)[number]);
  return i <= 0 ? 0 : i / (STEPS.length - 1);
}

export default function App() {
  const step = useQuote((s) => s.step);
  const setStep = useQuote((s) => s.setStep);
  const { catalogue, loading, error, retry } = useCatalogue();

  useStepHistory(step, setStep);

  return (
    <div className="min-h-dvh">
      {step !== "landing" && <ProgressBar value={progressFor(step)} />}

      <div className="mx-auto max-w-md px-4 pt-4">
        {step !== "landing" && (
          <p className="mb-3 text-sm font-semibold tracking-widest text-navy/50 uppercase">
            Myra Cleaning
          </p>
        )}

        {loading && <p className="py-16 text-center text-ink/60">Loading prices…</p>}

        {error && (
          <div className="flex flex-col gap-3 py-16">
            <Notice tone="error">Couldn&apos;t load prices. {error}</Notice>
            <Button onClick={retry}>Try again</Button>
          </div>
        )}

        {catalogue && (
          <>
            {step === "landing" && <Landing />}
            {step === "services" && <ChooseServices catalogue={catalogue} />}
            {step === "configure" && <Configure catalogue={catalogue} />}
            {step === "sitevisit" && <SiteVisit />}
            {step === "quote" && <QuoteSummary catalogue={catalogue} />}
            {step === "where" && <WhereWhen catalogue={catalogue} />}
            {step === "details" && <Details />}
            {step === "send" && <Send catalogue={catalogue} />}
          </>
        )}
      </div>
    </div>
  );
}
