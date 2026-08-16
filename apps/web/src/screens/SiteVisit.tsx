import { ActionBar, Button, Card, Chip, Field, Heading, Notice, Screen } from "../components/ui";
import { useQuote } from "../store/quote";

/**
 * §5.7 — the commercial / post-construction / "something else" branch.
 *
 * Deliberately shows NO total: these jobs vary too much to price blind, and
 * quoting them rigidly is how margin gets lost.
 */
export function SiteVisit() {
  const { siteVisit, items } = useQuote();
  const set = useQuote((s) => s.set);
  const setStep = useQuote((s) => s.setStep);
  const update = useQuote((s) => s.updateItem);

  const freeText = items.find((i) => i.service === "other");

  return (
    <Screen>
      <Heading sub="These jobs vary a lot, so we price them properly on a quick visit.">
        Tell us about the job
      </Heading>

      <Notice tone="warn">
        Big job — we&apos;ll confirm the exact price on a quick visit.
      </Notice>

      <Card>
        <h2 className="font-semibold text-navy">What kind of premises?</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {["Office", "BnB / Airbnb", "Shop", "Home", "Other"].map((p) => (
            <Chip
              key={p}
              selected={siteVisit.premises_type === p}
              onClick={() => set({ siteVisit: { ...siteVisit, premises_type: p } })}
            >
              {p}
            </Chip>
          ))}
        </div>

        <div className="mt-4 flex flex-col gap-4">
          <Field
            label="Rough size"
            value={siteVisit.rough_size ?? ""}
            onChange={(e) => set({ siteVisit: { ...siteVisit, rough_size: e.target.value } })}
            placeholder="e.g. 3 floors, 8 rooms"
          />

          {freeText && (
            <Field
              label="What do you need cleaned?"
              value={freeText.note ?? ""}
              onChange={(e) => update(freeText.uid, { note: e.target.value })}
              placeholder="Tell us in your own words"
            />
          )}
        </div>

        <h2 className="mt-4 font-semibold text-navy">How often?</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["one_off", "weekly", "fortnightly", "monthly"] as const).map((f) => (
            <Chip
              key={f}
              selected={siteVisit.frequency === f}
              onClick={() => set({ siteVisit: { ...siteVisit, frequency: f } })}
            >
              {f === "one_off" ? "One-off" : f[0]!.toUpperCase() + f.slice(1)}
            </Chip>
          ))}
        </div>
      </Card>

      <ActionBar>
        <Button full onClick={() => setStep("where")}>
          Continue
        </Button>
      </ActionBar>
    </Screen>
  );
}
