import { ActionBar, Button, Card, Chip, Field, Heading, Screen } from "../components/ui";
import { isValidKenyanMobile } from "../lib/format";
import { useQuote } from "../store/quote";

/** Step 5 — name (required), WhatsApp number (optional), tax-invoice toggle (§5, §6a). */
export function Details() {
  const { name, phone, needsTaxInvoice, businessName, kraPin } = useQuote();
  const set = useQuote((s) => s.set);
  const setStep = useQuote((s) => s.setStep);

  const phoneError = phone.trim() && !isValidKenyanMobile(phone) ? "Check this number" : "";
  const canContinue = name.trim().length > 0 && !phoneError;

  return (
    <Screen>
      <Heading sub="Only used to send your quote. No spam.">Your details</Heading>

      <Card>
        <div className="flex flex-col gap-4">
          <Field
            label="Your name"
            value={name}
            onChange={(e) => set({ name: e.target.value })}
            autoComplete="name"
            placeholder="Faith"
          />
          <Field
            label="WhatsApp number (optional)"
            value={phone}
            onChange={(e) => set({ phone: e.target.value })}
            inputMode="tel"
            autoComplete="tel"
            placeholder="0716 869 648"
            error={phoneError}
          />
        </div>
      </Card>

      <Card>
        <Chip
          selected={needsTaxInvoice}
          onClick={() => set({ needsTaxInvoice: !needsTaxInvoice })}
        >
          {needsTaxInvoice ? "✓ " : ""}I need a tax invoice (for my business)
        </Chip>

        {needsTaxInvoice && (
          <div className="mt-4 flex flex-col gap-4">
            <Field
              label="Business name"
              value={businessName}
              onChange={(e) => set({ businessName: e.target.value })}
              placeholder="Kevin's BnB"
            />
            <Field
              label="KRA PIN"
              value={kraPin}
              onChange={(e) => set({ kraPin: e.target.value.toUpperCase() })}
              placeholder="A012345678Z"
            />
            <p className="text-sm text-ink/60">
              A KRA-compliant eTIMS tax invoice will be issued on payment.
            </p>
          </div>
        )}
      </Card>

      <ActionBar>
        <Button full disabled={!canContinue} onClick={() => setStep("send")}>
          Continue
        </Button>
      </ActionBar>
    </Screen>
  );
}
