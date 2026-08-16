import { ActionBar, Button, Card, Chip, Field, Heading, Notice, Screen } from "../components/ui";
import { isoDayOffset } from "../lib/format";
import type { Catalogue } from "../lib/useCatalogue";
import { useQuote } from "../store/quote";

/** Step 4 — area, optional estate, preferred day + window (§5). */
export function WhereWhen({ catalogue }: { catalogue: Catalogue }) {
  const { area, estate, day, window: win, recurring } = useQuote();
  const set = useQuote((s) => s.set);
  const setStep = useQuote((s) => s.setStep);

  const selectedArea = catalogue.areas.find((a) => a.key === area);

  return (
    <Screen>
      <Heading sub="Timing is a preference — Mercy confirms the slot on WhatsApp.">
        Where &amp; when
      </Heading>

      <Card>
        <h2 className="font-semibold text-navy">Your area</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {catalogue.areas.map((a) => (
            <Chip key={a.key} selected={area === a.key} onClick={() => set({ area: a.key })}>
              {a.label}
            </Chip>
          ))}
        </div>

        {selectedArea?.visit && (
          <div className="mt-3">
            {/* A coverage question, not a pricing one — the total stays. */}
            <Notice>We&apos;ll confirm we cover you.</Notice>
          </div>
        )}

        <div className="mt-3">
          <Field
            label="Estate, building or landmark"
            hint="Helps Mercy find you — it goes on the quote."
            value={estate}
            onChange={(e) => set({ estate: e.target.value })}
            placeholder="e.g. Kasarani, Membley, Block C"
          />
        </div>

        <p className="mt-3 text-sm text-ink/55">
          Transport is charged separately by area — confirmed on WhatsApp.
        </p>
      </Card>

      <Card>
        <h2 className="font-semibold text-navy">Preferred day</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip selected={day === isoDayOffset(0)} onClick={() => set({ day: isoDayOffset(0) })}>
            Today
          </Chip>
          <Chip selected={day === isoDayOffset(1)} onClick={() => set({ day: isoDayOffset(1) })}>
            Tomorrow
          </Chip>
        </div>
        <div className="mt-3">
          <Field
            label="Or pick a date"
            type="date"
            value={day ?? ""}
            min={isoDayOffset(0)}
            onChange={(e) => set({ day: e.target.value || null })}
          />
        </div>

        <h2 className="mt-4 font-semibold text-navy">Time of day</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["morning", "afternoon"] as const).map((w) => (
            <Chip key={w} selected={win === w} onClick={() => set({ window: w })}>
              {w[0]!.toUpperCase() + w.slice(1)}
            </Chip>
          ))}
        </div>
      </Card>

      <Card>
        <Chip selected={recurring} onClick={() => set({ recurring: !recurring })}>
          {recurring ? "✓ " : ""}I&apos;ll want this regularly
        </Chip>
        {/* Intent, not a price lever. The rate is earned on the next clean, so
            this never changes today's total. */}
        <p className="mt-2 text-sm text-ink/55">
          Every clean after your first is {catalogue.rules.recurring_discount_pct}% off.
        </p>
      </Card>

      <ActionBar>
        <Button full disabled={!area} onClick={() => setStep("details")}>
          Continue
        </Button>
      </ActionBar>
    </Screen>
  );
}
