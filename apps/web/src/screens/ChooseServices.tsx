import { useMemo } from "react";

import { ActionBar, Button, Heading, Notice, Screen, SelectCard } from "../components/ui";
import { ksh } from "../lib/format";
import type { Catalogue } from "../lib/useCatalogue";
import { needsSiteVisit, toChosenServices, useQuote, VISIT_SERVICES } from "../store/quote";

/** Step 1 — multi-select service cards (§5). At least one to continue (§9). */
export function ChooseServices({ catalogue }: { catalogue: Catalogue }) {
  const items = useQuote((s) => s.items);
  const chosen = useMemo(() => toChosenServices(items), [items]);
  const toggleService = useQuote((s) => s.toggleService);
  const setStep = useQuote((s) => s.setStep);
  const visitBranch = useQuote(needsSiteVisit);

  const hint = (key: string, fromLabel?: number | null) => {
    if (VISIT_SERVICES.has(key)) return "Site visit";
    return fromLabel ? `from ${ksh(fromLabel)}` : undefined;
  };

  return (
    <Screen>
      <Heading sub="Pick everything you need — you can add more later.">
        What needs cleaning?
      </Heading>

      <div className="flex flex-col gap-2">
        {catalogue.services.map((svc) => (
          <SelectCard
            key={svc.key}
            selected={chosen.has(svc.key)}
            icon={svc.icon}
            title={svc.label}
            hint={hint(svc.key, svc.from_label)}
            onClick={() => toggleService(svc.key)}
          />
        ))}
      </div>

      {chosen.size === 0 && <Notice>Pick at least one to see your price.</Notice>}

      {visitBranch && (
        <Notice tone="warn">
          Big job — we&apos;ll confirm the exact price on a quick visit.
        </Notice>
      )}

      <ActionBar>
        <Button
          full
          disabled={chosen.size === 0}
          onClick={() => setStep(visitBranch ? "sitevisit" : "configure")}
        >
          {visitBranch ? "Tell us about the job" : "Continue"}
        </Button>
      </ActionBar>
    </Screen>
  );
}
