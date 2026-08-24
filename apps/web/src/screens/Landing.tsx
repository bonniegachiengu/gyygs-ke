import { Button, Screen } from "../components/ui";
import { useQuote } from "../store/quote";

/** Step 0 — QUOTE_CALCULATOR_SPEC §5. Navy hero, green CTA, trust strip. */
export function Landing() {
  const setStep = useQuote((s) => s.setStep);

  return (
    <Screen>
      <div className="-mx-4 -mt-4 rounded-b-3xl bg-navy px-6 pt-12 pb-10 text-white">
        <p className="text-sm font-semibold tracking-widest text-white/70 uppercase">
          Myrah Cleaning Services
        </p>
        <h1 className="mt-3 text-3xl leading-tight font-bold">
          Get your cleaning price in 30 seconds
        </h1>
        <p className="mt-3 text-white/80">
          Fixed prices. No haggling. A small deposit holds your slot.
        </p>
        <Button full className="mt-6" onClick={() => setStep("services")}>
          Start my quote
        </Button>
      </div>

      <ul className="flex flex-wrap gap-x-3 gap-y-1 px-1 text-sm text-ink/60">
        {["Fixed prices", "No haggling", "We come to you"].map((t) => (
          <li key={t} className="flex items-center gap-1">
            <span aria-hidden="true" className="text-green">
              ✓
            </span>
            {t}
          </li>
        ))}
      </ul>
      <p className="px-1 text-sm text-ink/60">Nairobi · Ruiru · Thika · Juja · Kiambu</p>
    </Screen>
  );
}
