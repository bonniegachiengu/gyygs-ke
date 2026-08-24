/**
 * OFFLINE FALLBACK ONLY.
 *
 * The server builds the real handoff (ARCHITECTURE §11) and the Send button uses
 * its `whatsapp_url` on the happy path. This exists solely for
 * QUOTE_CALCULATOR_SPEC §9: "server quote submit retries, never blocks the
 * handoff." If the POST is still failing after a couple of seconds, the customer
 * can still reach Mercy.
 *
 * The trade-off is explicit: a quote sent this way is NOT logged as a lead, and
 * it carries no quote reference. It uses the same label grammar as the server so
 * the numbers Mercy receives are still right.
 */

import type { Estimate } from "./pricing/estimate";

const RULE = "—".repeat(14);
const money = (n: number) => `KSh ${n.toLocaleString("en-US")}`;

export function buildFallbackText({
  estimate,
  areaLabel,
  preferred,
  name,
  siteHost,
}: {
  estimate: Estimate;
  areaLabel: string;
  preferred: string | null;
  name: string;
  siteHost: string;
}): string {
  const out: string[] = ["Hi Myrah Cleaning 👋 I'd like to book this quote:", ""];

  for (const line of estimate.lines) out.push(`• ${line.label}: ${money(line.amount)}`);
  out.push(RULE);

  out.push(
    estimate.visitFirst
      ? `Estimated total: from ${money(estimate.total)} (final price confirmed on a quick site visit)`
      : `Estimated total: ${money(estimate.total)}`,
  );
  out.push("Transport: charged separately by area");

  let areaLine = `Area: ${areaLabel}`;
  if (preferred) areaLine += `  ·  Preferred: ${preferred}`;
  out.push(areaLine);
  out.push(`Name: ${name}`);

  out.push("", `(Quote pending · from ${siteHost})`);
  return out.join("\n");
}

export const waUrl = (text: string, number: string): string =>
  `https://wa.me/${number}?text=${encodeURIComponent(text)}`;

export const webWaUrl = (text: string, number: string): string =>
  `https://web.whatsapp.com/send?phone=${number}&text=${encodeURIComponent(text)}`;

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Older Android WebViews without the async clipboard API.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}
