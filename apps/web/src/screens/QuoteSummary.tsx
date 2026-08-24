import { useMemo } from "react";

import { ActionBar, Button, Card, Heading, Notice, Screen } from "../components/ui";
import { ksh } from "../lib/format";
import { estimate } from "../lib/pricing/estimate";
import type { Catalogue } from "../lib/useCatalogue";
import { toDraftAddons, toDraftItems, useQuote } from "../store/quote";

/**
 * Step 3 — the live itemised quote (§5).
 *
 * This is the client-side ESTIMATE. The server total is the quote of record and
 * replaces it on the Send step (§6).
 */
export function QuoteSummary({ catalogue }: { catalogue: Catalogue }) {
  const rawItems = useQuote((s) => s.items);
  const rawAddons = useQuote((s) => s.addons);
  const recurring = useQuote((s) => s.recurring);
  const setStep = useQuote((s) => s.setStep);

  const items = useMemo(() => toDraftItems(rawItems), [rawItems]);
  const addons = useMemo(() => toDraftAddons(rawAddons), [rawAddons]);
  const est = useMemo(
    () => estimate(catalogue, items, addons, recurring),
    [catalogue, items, addons, recurring],
  );

  return (
    <Screen>
      <Heading>Your quote</Heading>

      <Card>
        <ul className="flex flex-col gap-2">
          {est.lines.map((line, i) => (
            <li key={`${line.label}-${i}`} className="flex items-baseline justify-between gap-3">
              <span className="text-sm text-ink/80">{line.label}</span>
              <span className="shrink-0 font-medium tabular-nums text-navy">
                {ksh(line.amount)}
              </span>
            </li>
          ))}
        </ul>

        <div className="mt-4 border-t border-navy/10 pt-3">
          <Row label="Subtotal" value={ksh(est.subtotal)} muted />

          {est.discount > 0 && (
            <Row
              label={`Recurring discount (${catalogue.rules.recurring_discount_pct}%)`}
              value={`−${ksh(est.discount)}`}
              muted
            />
          )}

          {/* Shown rather than folded into the total, so the card still adds up. */}
          {est.minimumApplied && (
            <Row label="Minimum call-out" value={ksh(est.minimumAdjustment)} muted />
          )}

          <div className="mt-2 flex items-baseline justify-between gap-3 border-t border-navy/10 pt-2">
            <span className="font-semibold text-navy">
              {est.visitFirst ? "Estimated from" : "Estimated total"}
            </span>
            <span className="text-2xl font-bold tabular-nums text-navy">
              {est.visitFirst ? `from ${ksh(est.total)}` : ksh(est.total)}
            </span>
          </div>
        </div>

        <p className="mt-3 text-sm text-ink/55">
          {est.visitFirst
            ? "Priced on a quick visit · transport charged separately"
            : `Fixed price · transport charged separately · ${catalogue.rules.deposit_pct}% to book, balance after the clean`}
        </p>

        {/* Unconditional: this screen is where the price lands, so it is where
            the incentive to book again belongs — and it comes before the
            "I'll want this regularly" checkbox on the next step anyway.
            A promise about the NEXT clean, never a discount on this one, so
            today's number stays honest and nothing is given away to a customer
            who may never come back. */}
        {catalogue.rules.recurring_discount_pct > 0 && (
          <p className="mt-2 rounded-xl bg-green/10 px-3 py-2 text-sm font-medium text-green-deep">
            Booking again? Every clean after your first is{" "}
            {catalogue.rules.recurring_discount_pct}% off.
          </p>
        )}
      </Card>

      {est.minimumApplied && (
        <Notice>
          Our minimum call-out is {ksh(catalogue.minimum_callout)} — that&apos;s what a visit
          costs us either way.
        </Notice>
      )}

      {est.visitFirst && (
        <Notice tone="warn">
          Big job — we&apos;ll confirm the exact price on a quick visit.
        </Notice>
      )}

      <Button variant="secondary" onClick={() => setStep("configure")}>
        Edit my selection
      </Button>

      <ActionBar>
        <Button full onClick={() => setStep("where")}>
          Continue
        </Button>
      </ActionBar>
    </Screen>
  );
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className={`text-sm ${muted ? "text-ink/60" : "text-navy"}`}>{label}</span>
      <span className="text-sm tabular-nums text-ink/80">{value}</span>
    </div>
  );
}
