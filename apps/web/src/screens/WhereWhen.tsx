import { ActionBar, Button, Card, Chip, Field, Heading, Screen } from "../components/ui";
import { isoDayOffset } from "../lib/format";
import type { Catalogue } from "../lib/useCatalogue";
import { needsSiteVisit, useQuote } from "../store/quote";

/**
 * Step 4 — area, optional estate, preferred day + window (§5).
 *
 * THE AREA IS COLLECTED HERE WHEN IT IS MISSING, and that is the fix for a live
 * dead end (25 Aug 2026). `area` used to be settable on ONE screen — the quote
 * summary — but a basket needing a site visit branches around that screen
 * entirely (ChooseServices -> sitevisit -> here). Those customers arrived with
 * `area` still null, hit `disabled={!area}` on a Continue that never explained
 * itself, and had no control on this screen that could set it and no way back.
 *
 * A screen must never gate on something it does not let you supply. Asking for
 * the area here is also just correct on its own terms: this is the "where"
 * screen, and for a site-visit job there is no price for the area to change.
 */
export function WhereWhen({ catalogue }: { catalogue: Catalogue }) {
  const { area, estate, day, window: win, recurring } = useQuote();
  const set = useQuote((s) => s.set);
  const setStep = useQuote((s) => s.setStep);
  const visitBranch = useQuote(needsSiteVisit);

  const selectedArea = catalogue.areas.find((a) => a.key === area);

  return (
    <Screen>
      <Heading sub="Timing is a preference — Mercy confirms the slot on WhatsApp.">
        Where &amp; when
      </Heading>

      <Card>
        <h2 className="font-semibold text-navy">Where exactly?</h2>
        {selectedArea ? (
          <p className="mt-1 text-sm text-ink/60">
            {selectedArea.label} —{" "}
            {visitBranch
              ? "transport is confirmed with your quote."
              : "chosen with your price."}
          </p>
        ) : (
          <>
            {/* Reached only on the site-visit route, which has no price screen. */}
            <p className="mt-1 text-sm text-ink/60">
              Which area are you in? Mercy needs it to plan the visit.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {catalogue.areas.map((a) => (
                <Chip
                  key={a.key}
                  selected={area === a.key}
                  onClick={() => set({ area: a.key })}
                >
                  {a.label}
                </Chip>
              ))}
            </div>
          </>
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
        {!area && (
          <p className="text-center text-sm text-ink/60">
            Pick your area above to continue.
          </p>
        )}
        <Button full disabled={!area} onClick={() => setStep("details")}>
          Continue
        </Button>
      </ActionBar>
    </Screen>
  );
}
