/**
 * "What's included" copy for the service picker accordion.
 *
 * ⚠️ FIRST DRAFT — written from PRICES.md and the pricing engine, NOT from
 * Mercy. Every string here needs her eye before it goes live: she knows what a
 * job actually involves and what clients ask on WhatsApp. Wording is kept in
 * this one file precisely so she and Bonnie can rewrite it without going near a
 * component.
 *
 * WHY THIS EXISTS: the cards used to say "Sofa — from KSh 500" and nothing
 * else. A client cannot tell what that covers, that it is per SEAT, or that
 * "from" means the cheapest case. That guesswork is what the accordion removes.
 *
 * `priced` must stay factually true to app/domain/pricing_data.py. If a price
 * basis changes there, change it here in the same commit — a wrong explanation
 * is worse than none.
 */

export type ServiceDetail = {
  /** One line: what the client actually gets. */
  includes: string;
  /** How the number is arrived at. Answers "from what?" and "per what?". */
  priced: string;
  /** Optional: the thing clients most often get wrong or ask about. */
  note?: string;
};

export const SERVICE_DETAILS: Record<string, ServiceDetail> = {
  house: {
    includes:
      "A full deep clean of the whole place — floors, surfaces, kitchen, bathrooms, inside cupboards, windows from the inside, and skirting.",
    priced:
      "Priced by the size of the home, from a studio up to 4 bedrooms. Larger places are quoted from there — an extra bedroom is added on top.",
    note: "Furniture and carpets are separate — add them below if you want them done in the same visit.",
  },
  sofa: {
    includes:
      "Deep shampoo and extraction of the fabric — the dirt that lives inside the cushion, not just the surface.",
    priced:
      "Priced per seat, so a 3-seater is three. A single armchair counts as one seat — there is no minimum.",
    note: "Dining and office chairs can be added too.",
  },
  carpet: {
    includes:
      "Shampoo, extraction and deodorising, edge to edge.",
    priced:
      "Priced by the size of the carpet, from a small 3×5 up to a large 10×14.",
    note: "Thick or shaggy carpets take longer to clean and dry, so they cost a little more.",
  },
  curtains: {
    includes:
      "Taken down, cleaned, dried and re-hung.",
    priced:
      "Priced per panel, by weight of fabric — light sheers cost less than heavy lined curtains.",
    note: "Count each panel separately, not each window.",
  },
  mattress: {
    includes:
      "Deep clean of both sides, with stain treatment and sanitising.",
    priced: "Priced by mattress size.",
  },
  post_construction: {
    includes:
      "The heavy clean after building or renovation — dust, paint, cement and debris removal.",
    priced:
      "Every site is different, so we look first and then give you an exact price. No obligation.",
  },
  commercial: {
    includes:
      "Offices, shops, BnBs and other business premises — one-off or on a regular schedule.",
    priced:
      "Quoted after a quick visit so the price fits the actual space and how often you need it.",
  },
  other: {
    includes: "Anything not on this list — just tell us what you need.",
    priced: "We will look at it and come back to you with a price.",
  },
};

export function serviceDetail(key: string): ServiceDetail | undefined {
  return SERVICE_DETAILS[key];
}
