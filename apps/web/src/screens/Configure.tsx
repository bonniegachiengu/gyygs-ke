import {
  ActionBar,
  Button,
  Card,
  Chip,
  Counter,
  Heading,
  Screen,
  VisitBadge,
} from "../components/ui";
import { ksh } from "../lib/format";
import type { Catalogue } from "../lib/useCatalogue";
import { useQuote, type DraftItemWithId } from "../store/quote";

/** Step 2 — only the configurators for what was actually chosen (§5). */
export function Configure({ catalogue }: { catalogue: Catalogue }) {
  const items = useQuote((s) => s.items);
  const setStep = useQuote((s) => s.setStep);

  return (
    <Screen>
      <Heading sub="Sizes and counts come straight from Myra's price list.">
        Tell us the details
      </Heading>

      {items.map((item) => (
        <ItemConfig key={item.uid} item={item} catalogue={catalogue} />
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

function ItemConfig({ item, catalogue }: { item: DraftItemWithId; catalogue: Catalogue }) {
  const svc = catalogue.services.find((s) => s.key === item.service);
  const update = useQuote((s) => s.updateItem);
  if (!svc) return null;

  return (
    <Card>
      <h2 className="flex items-center gap-2 font-semibold text-navy">
        {svc.icon && <span aria-hidden="true">{svc.icon}</span>}
        {svc.label}
      </h2>

      {svc.strategy === "per_unit" && (
        <div className="mt-3 flex flex-col gap-3">
          <Row label={`How many ${svc.unit}s?`}>
            <Counter
              label={`${svc.unit}s`}
              value={item.seats ?? svc.min_units ?? 2}
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
      )}

      {svc.strategy === "tier" && (
        <div className="mt-3 flex flex-col gap-3">
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
      )}

      {svc.strategy === "size_tier" && (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            {(svc.tiers ?? []).map((tier) => (
              <Chip
                key={tier.key}
                selected={item.size === tier.key}
                onClick={() => update(item.uid, { size: tier.key })}
              >
                {tier.label} ft · {ksh(tier.price)}
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
      )}
    </Card>
  );
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
