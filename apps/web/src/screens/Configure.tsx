import { useMemo } from "react";

import {
  ActionBar,
  Button,
  Card,
  Chip,
  Counter,
  Heading,
  Notice,
  Screen,
  VisitBadge,
} from "../components/ui";
import { ksh } from "../lib/format";
import { isConfigured } from "../lib/pricing/estimate";
import type { Catalogue } from "../lib/useCatalogue";
import { useQuote, type DraftItemWithId } from "../store/quote";

type Service = Catalogue["services"][number];

/**
 * Step 2 — only the configurators for what was actually chosen (§5).
 *
 * Each service holds one or more LINES. Two heavy curtains, two sheers and one
 * standard is three lines under a single Curtains card. The engine has always
 * accepted that (items is a list, and each is priced independently); this screen
 * used to be the thing that could not express it.
 */
export function Configure({ catalogue }: { catalogue: Catalogue }) {
  const items = useQuote((s) => s.items);
  const setStep = useQuote((s) => s.setStep);

  // Group lines under their service, keeping the order the services were picked.
  const groups = useMemo(() => {
    const order: string[] = [];
    const byService = new Map<string, DraftItemWithId[]>();
    for (const item of items) {
      let rows = byService.get(item.service);
      if (!rows) {
        rows = [];
        byService.set(item.service, rows);
        order.push(item.service);
      }
      rows.push(item);
    }
    return order.map((key) => ({ key, rows: byService.get(key) ?? [] }));
  }, [items]);

  return (
    <Screen>
      <Heading sub="Sizes and counts come straight from Myra's price list.">
        Tell us the details
      </Heading>

      {groups.map((group) => (
        <ServiceGroup key={group.key} rows={group.rows} catalogue={catalogue} />
      ))}

      <AddonsPicker catalogue={catalogue} />

      <ActionBar>
        <Button full onClick={() => setStep("quote")}>
          See my price
        </Button>
      </ActionBar>
    </Screen>
  );
}

function ServiceGroup({
  rows,
  catalogue,
}: {
  rows: DraftItemWithId[];
  catalogue: Catalogue;
}) {
  const addItem = useQuote((s) => s.addItem);
  const removeItem = useQuote((s) => s.removeItem);

  const svc = catalogue.services.find((s) => s.key === rows[0]?.service);
  if (!svc) return null;

  // A house is one house. Curtains, carpets, mattresses and sofas come in
  // assorted sizes, so those repeat.
  const repeatable = svc.strategy === "size_tier" || svc.strategy === "per_unit";

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-semibold text-navy">
        {svc.icon && <span aria-hidden="true">{svc.icon}</span>}
        {svc.label}
      </h2>

      {rows.map((item, index) => (
        <div
          key={item.uid}
          className={index > 0 ? "mt-4 border-t border-navy/10 pt-4" : "mt-3"}
        >
          {rows.length > 1 && (
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold tracking-wider text-ink/45 uppercase">
                {svc.label} {index + 1}
              </span>
              <button
                type="button"
                onClick={() => removeItem(item.uid)}
                className="min-h-12 px-2 text-sm font-medium text-red-700 underline"
                aria-label={`Remove ${svc.label} ${index + 1}`}
              >
                Remove
              </button>
            </div>
          )}

          <ItemFields item={item} svc={svc} />

          {!isConfigured(item, catalogue) && (
            <div className="mt-2">
              <Notice>Pick an option above to include this one in your price.</Notice>
            </div>
          )}
        </div>
      ))}

      {repeatable && (
        // Just "Add another" — the button sits inside the service's own card, and
        // lowercasing the label produced "Add another curtains".
        <Button variant="secondary" className="mt-4" onClick={() => addItem(svc.key)}>
          + Add another
        </Button>
      )}
    </Card>
  );
}

function ItemFields({ item, svc }: { item: DraftItemWithId; svc: Service }) {
  const update = useQuote((s) => s.updateItem);

  if (svc.strategy === "per_unit") {
    return (
      <div className="flex flex-col gap-3">
        <Row label={`How many ${svc.unit}s?`}>
          <Counter
            label={`${svc.unit}s`}
            value={item.seats ?? svc.min_units ?? 1}
            min={svc.min_units ?? 1}
            max={svc.max_units ?? 20}
            onChange={(seats) => update(item.uid, { seats })}
          />
        </Row>
        {(svc.extras ?? []).map((extra) => {
          const current = (item.extras ?? []).find((e) => e.key === extra.key)?.qty ?? 0;
          return (
            <Row key={extra.key} label={`${extra.label} · ${ksh(extra.price)} each`}>
              <Counter
                label={extra.label}
                value={current}
                min={0}
                onChange={(qty) => {
                  const others = (item.extras ?? []).filter((e) => e.key !== extra.key);
                  update(item.uid, {
                    extras: qty > 0 ? [...others, { key: extra.key, qty }] : others,
                  });
                }}
              />
            </Row>
          );
        })}
      </div>
    );
  }

  if (svc.strategy === "tier") {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {(svc.tiers ?? []).map((tier) => (
            <Chip
              key={tier.key}
              selected={item.tier === tier.key}
              onClick={() => update(item.uid, { tier: tier.key })}
            >
              {tier.label} · {ksh(tier.price)}
            </Chip>
          ))}
        </div>
        {svc.extra && item.tier === (svc.tiers ?? []).at(-1)?.key && (
          <Row label={`${svc.extra.label} · ${ksh(svc.extra.price)} each`}>
            <Counter
              label={svc.extra.label}
              value={item.extra_bedrooms ?? 0}
              min={0}
              max={10}
              onChange={(extra_bedrooms) => update(item.uid, { extra_bedrooms })}
            />
          </Row>
        )}
      </div>
    );
  }

  if (svc.strategy === "size_tier") {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {(svc.tiers ?? []).map((tier) => (
            <Chip
              key={tier.key}
              selected={item.size === tier.key}
              onClick={() => update(item.uid, { size: tier.key })}
            >
              {tier.label}
              {svc.tier_unit ? ` ${svc.tier_unit}` : ""} · {ksh(tier.price)}
            </Chip>
          ))}
          {svc.above && (
            <Chip
              selected={item.size === svc.above.key}
              onClick={() => update(item.uid, { size: svc.above!.key })}
            >
              {svc.above.label} · from {ksh(svc.above.price)}
            </Chip>
          )}
          {svc.larger === "visit" && (
            <Chip
              selected={item.size === "larger"}
              onClick={() => update(item.uid, { size: "larger" })}
            >
              Larger
            </Chip>
          )}
        </div>

        {(item.size === "larger" || (svc.above && item.size === svc.above.key)) && (
          <VisitBadge />
        )}

        {(svc.modifiers ?? []).map((mod) => {
          const on = (item.modifiers ?? []).includes(mod.key);
          const range = mod.add_range;
          return (
            <div key={mod.key}>
              <Chip
                selected={on}
                onClick={() =>
                  update(item.uid, {
                    modifiers: on
                      ? (item.modifiers ?? []).filter((m) => m !== mod.key)
                      : [...(item.modifiers ?? []), mod.key],
                  })
                }
              >
                {mod.label}
                {range ? ` +${range[0]}–${range[1]}` : ""}
              </Chip>
              {on && <VisitBadge />}
            </div>
          );
        })}

        <Row label="How many?">
          <Counter
            label={svc.label}
            value={item.qty ?? 1}
            min={1}
            onChange={(qty) => update(item.uid, { qty })}
          />
        </Row>
      </div>
    );
  }

  return null;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-ink/70">{label}</span>
      {children}
    </div>
  );
}

/** Add-on chips, shown once any service is chosen (§5 Step 2). */
function AddonsPicker({ catalogue }: { catalogue: Catalogue }) {
  const addons = useQuote((s) => s.addons);
  const setAddonQty = useQuote((s) => s.setAddonQty);

  return (
    <Card>
      <h2 className="font-semibold text-navy">Anything else?</h2>
      <p className="mt-1 text-sm text-ink/60">Optional extras.</p>

      <div className="mt-3 flex flex-col gap-2">
        {catalogue.addons.map((addon) => {
          const qty = addons[addon.key] ?? 0;
          const price = addon.price_range
            ? `${ksh(addon.price_range[0] ?? 0)}–${ksh(addon.price_range[1] ?? 0)}`
            : addon.from
              ? `from ${ksh(addon.price ?? 0)}`
              : ksh(addon.price ?? 0);
          const isVisit = Boolean(addon.price_range || addon.from);

          return (
            <div key={addon.key} className="flex items-center justify-between gap-3">
              <span className="flex-1">
                <span className="block text-sm font-medium text-navy">{addon.label}</span>
                <span className="block text-sm text-ink/55">
                  {price}
                  {addon.per === "unit" ? " each" : ""}
                </span>
                {isVisit && qty > 0 && <VisitBadge />}
              </span>
              {addon.per === "unit" ? (
                <Counter
                  label={addon.label}
                  value={qty}
                  min={0}
                  onChange={(next) => setAddonQty(addon.key, next)}
                />
              ) : (
                <Chip selected={qty > 0} onClick={() => setAddonQty(addon.key, qty > 0 ? 0 : 1)}>
                  {qty > 0 ? "Added" : "Add"}
                </Chip>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
