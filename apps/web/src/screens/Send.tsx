import { useEffect, useMemo, useRef, useState } from "react";

import { ActionBar, Button, Card, Heading, Notice, Screen } from "../components/ui";
import { api } from "../lib/api/client";
import { formatPreferred, ksh } from "../lib/format";
import { estimate, isConfigured } from "../lib/pricing/estimate";
import type { Catalogue } from "../lib/useCatalogue";
import { buildFallbackText, copyToClipboard, waUrl, webWaUrl } from "../lib/whatsapp";
import { toDraftAddons, toDraftItems, useQuote } from "../store/quote";

const FALLBACK_AFTER_MS = 2500;

/**
 * Step 6 — the handoff (§5, §7).
 *
 * The POST happens here rather than earlier because `contact.name` is required by
 * the §5 request shape and is not known until Step 5 — and posting later means
 * one lead row per customer rather than a draft per keystroke.
 */
export function Send({ catalogue }: { catalogue: Catalogue }) {
  const state = useQuote();
  // Drop any line the customer added but never chose an option for. It prices
  // as nothing anyway, and the server rejects a size_tier item with no size as a
  // domain error — which would surface as a 400 at the worst possible moment.
  const items = useMemo(
    () => toDraftItems(state.items).filter((i) => isConfigured(i, catalogue)),
    [state.items, catalogue],
  );
  const addons = useMemo(() => toDraftAddons(state.addons), [state.addons]);
  const set = useQuote((s) => s.set);
  const setStep = useQuote((s) => s.setStep);

  const [failed, setFailed] = useState(false);
  const [allowFallback, setAllowFallback] = useState(false);
  const [copied, setCopied] = useState(false);
  const posted = useRef(false);

  const est = estimate(catalogue, items, addons, state.recurring);
  const areaLabel = catalogue.areas.find((a) => a.key === state.area)?.label ?? state.area ?? "";
  const preferred = formatPreferred(state.day ?? undefined, state.window ?? undefined);

  // §9: the handoff must never be blocked by the network.
  useEffect(() => {
    const t = setTimeout(() => setAllowFallback(true), FALLBACK_AFTER_MS);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (posted.current) return;
    posted.current = true;

    set({ submitting: true });
    void (async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        const result = await api
          .POST("/api/quote", {
            body: {
              items,
              addons,
              area: state.area ?? "",
              estate: state.estate.trim() || null,
              preferred:
                state.day || state.window
                  ? { day: state.day, window: state.window }
                  : null,
              contact: { name: state.name, phone: state.phone.trim() || null },
              recurring: state.recurring,
              business_name: state.needsTaxInvoice ? state.businessName || null : null,
              kra_pin: state.needsTaxInvoice ? state.kraPin || null : null,
              site_visit: Object.keys(state.siteVisit).length ? state.siteVisit : null,
            },
          })
          .catch(() => null);

        if (result?.data) {
          set({ server: result.data, submitting: false });
          return;
        }
        await new Promise((r) => setTimeout(r, 400 * 3 ** attempt));
      }
      set({ submitting: false });
      setFailed(true);
    })();
    // Intentionally once-only: this is the submit, not a subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The number comes from the catalogue, never a constant here — switching it
  // (e.g. to Bonnie's line for testing) must be a config change, not a rebuild.
  const number = catalogue.whatsapp_number;

  const fallbackText = buildFallbackText({
    estimate: est,
    areaLabel,
    preferred,
    name: state.name,
    siteHost: window.location.host,
  });

  const server = state.server;
  const href = server?.whatsapp_url ?? waUrl(fallbackText, number);
  const text = server ? decodeURIComponent(href.split("?text=")[1] ?? "") : fallbackText;
  const ready = Boolean(server) || allowFallback;

  const total = server?.total ?? est.total;
  const visitFirst = server?.visit_first ?? est.visitFirst;

  const onSend = () => {
    if (state.sent) return; // double-tap guard (§9)
    set({ sent: true });
    if (server) {
      // Fire-and-forget; mark_sent is idempotent server-side.
      navigator.sendBeacon?.(`/api/quote/${server.quote_ref}/sent`);
    }
  };

  if (state.sent) {
    return (
      <Screen>
        <Card>
          <p className="text-lg font-semibold text-navy">
            Sent! Mercy will confirm your slot shortly. 💚
          </p>
          {server && (
            <p className="mt-2 text-sm text-ink/60">Your reference: {server.quote_ref}</p>
          )}
        </Card>
        <Button variant="secondary" onClick={() => useQuote.getState().reset()}>
          Start another quote
        </Button>
      </Screen>
    );
  }

  return (
    <Screen>
      <Heading sub="Check it over, then send it to Mercy on WhatsApp.">Almost there</Heading>

      <Card>
        <ul className="flex flex-col gap-2">
          {(server?.lines ?? est.lines).map((line, i) => (
            <li key={`${line.label}-${i}`} className="flex items-baseline justify-between gap-3">
              <span className="text-sm text-ink/80">{line.label}</span>
              <span className="shrink-0 font-medium tabular-nums text-navy">
                {ksh(line.amount)}
              </span>
            </li>
          ))}
        </ul>

        <div className="mt-3 flex items-baseline justify-between gap-3 border-t border-navy/10 pt-3">
          <span className="font-semibold text-navy">
            {visitFirst ? "Estimated from" : "Estimated total"}
          </span>
          <span className="text-2xl font-bold tabular-nums text-navy">
            {visitFirst ? `from ${ksh(total)}` : ksh(total)}
          </span>
        </div>

        <p className="mt-3 text-sm text-ink/55">
          {server?.transport_note ??
            "Transport charged separately based on your area — confirmed on WhatsApp."}
        </p>
        <p className="mt-1 text-sm text-ink/55">
          {areaLabel}
          {state.estate.trim() ? ` — ${state.estate.trim()}` : ""}
          {preferred ? ` · ${preferred}` : ""} · {state.name}
        </p>
      </Card>

      {state.submitting && !ready && <Notice>Preparing your quote…</Notice>}

      {failed && (
        <Notice tone="warn">
          We couldn&apos;t save your quote just now, but you can still send it — Mercy will
          get everything.
        </Notice>
      )}

      <div className="flex flex-col gap-2">
        <Button
          variant="secondary"
          onClick={() => {
            void copyToClipboard(text).then(setCopied);
          }}
        >
          {copied ? "Copied ✓" : "Copy quote"}
        </Button>
        <a
          className="inline-flex min-h-12 items-center justify-center rounded-xl px-5 text-base font-semibold text-navy ring-1 ring-navy/20"
          href={`tel:+${number}`}
        >
          Call instead
        </a>
        <a
          className="text-center text-sm text-ink/50 underline"
          href={webWaUrl(text, number)}
          target="_blank"
          rel="noreferrer"
        >
          No WhatsApp app? Open WhatsApp Web
        </a>
      </div>

      <Button variant="ghost" onClick={() => setStep("quote")}>
        Back to my quote
      </Button>

      <ActionBar>
        <a
          href={ready ? href : undefined}
          onClick={ready ? onSend : (e) => e.preventDefault()}
          aria-disabled={!ready}
          className={[
            "inline-flex min-h-12 w-full items-center justify-center rounded-xl px-5",
            "text-base font-semibold text-white shadow-sm transition-colors",
            ready ? "bg-green hover:bg-green-deep" : "pointer-events-none bg-green/40",
          ].join(" ")}
        >
          Send my quote on WhatsApp
        </a>
      </ActionBar>
    </Screen>
  );
}
