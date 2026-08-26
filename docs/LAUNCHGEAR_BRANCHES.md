# LaunchGear — branch log

**Purpose:** LG work was done on a stack of branches because
`apps/launchgear/index.html` on `main` **is the live site**. nginx serves that
directory straight off disk on port 8080 with `Cache-Control: no-cache`, and
staging does not serve LG at all (`nginx-staging.conf`: *"n/a — staging serves
the app only"*). So a commit on `main` is a publish. Nothing here has been
merged; merging is Bonnie's call and his command.

**Last updated:** 26 Aug 2026.

---

## The stack

Each branch is one concern and sits on the one before it, so the tip contains
everything. Merge the tip for the lot, or merge them in order to review each
change on its own.

```
main
 └── feat/lg-launch-ready      28c8076   hook, example strip, intake, house style
      └── feat/lg-clips-flag   ea293c0   hide the empty clips gallery behind a flag
           └── feat/lg-share-preview  ed7f1c7   og: tags + link-preview card   <- TIP
```

**To take all of it:**

```
cd C:\Users\DELL\dev\gyygs.ke
git merge --no-ff feat/lg-share-preview
```

nginx picks it up on the next request. No build, no restart. The API is not
involved: nothing in this stack touches Python.

---

## What each branch does

### 1. `feat/lg-launch-ready` — 28c8076

**Why:** the page headline read *"busywork"*. The approved hook and all six ad
creatives say *"annoying work"*. Every ad click would have landed on a
different promise than the one it sold.

- Hook corrected in `<title>`, meta description and `<h1>`.
- Added the example strip under the hero, four rows naming a real build each
  (Myrah, VOS, 365+, NCS). It existed only in `LG_ADS.md` and had never been on
  the page, so the hook had nothing concrete under it. The first two run
  further down the same page, so the claim is checkable in one scroll.
- The three WhatsApp CTAs opened an empty chat. They now prefill *"the thing
  that eats my day is:"*, the same funnel pattern Myrah uses.
- Em-dash asides out of the page's own copy. The embedded Myrah demo keeps its
  labels, since it replicates that tool's real UI.
- Dropped *"being filmed this week"*, a dated promise about clips that do not
  exist.

### 2. `feat/lg-clips-flag` — ea293c0

**Why:** section 03 was four cards reading *"recording to come"*, and it is the
first section a visitor meets after the two live demos. On a launch page that
reads unfinished.

- `<html data-clips="off">` hides it. `"on"` brings it back. The markup is
  untouched and complete, so shipping it later is a one-word edit.
- Hiding a numbered section would have left the page reading 02, 04, 05, 06, so
  each later index carries both numbers and CSS picks the right one. Flipping
  the flag fixes the numbering in the same stroke. No JS.
- The rule above the section is hidden with it, or two rules would sit together
  with nothing between them.
- **Fails safe:** a missing or unrecognised value falls back to showing the
  section with its real numbering, so a typo can never blank a number.
- Verified in a real engine across all four states (missing / off / on /
  unknown). Exactly one number span is visible in every state.

### 3. `feat/lg-share-preview` — ed7f1c7  ← tip

**Why:** the page had no Open Graph or Twitter tags at all. The ads point here
and most sharing happens on WhatsApp, where a link with no `og:image` renders
as a bare grey URL. Every share of the campaign's own landing page looked
broken.

- `og:` / `twitter:` tags, a canonical and a `theme-color`.
- New `apps/launchgear/og-1200x630.png`, built from the page's own Fraunces and
  Space Grotesk in its own palette, carrying the same two proofs the page leads
  with, including *"M-Pesa and bank messages"* so it agrees with the creatives.
- Canonical points at `lg.*`, the host printed on every creative.
  `launchgear.*` serves the same site and should not compete with it in search.

---

## Decisions taken, and why

**Hide the clips section rather than delete it.** Deleting loses the layout and
the copy; a flag keeps both and makes shipping it a one-word change. The cards
are real plans, not filler, so they should come back.

**Do not renumber in markup.** Both numbers ship and CSS chooses. If the CSS
ever fails to load, the fallback shows the true numbering rather than nothing.

**Leave the embedded Myrah demo's em-dashes.** Those labels replicate Myrah's
real UI. Rewriting them would make the demo stop matching the tool it
demonstrates.

**Ad copy fix lives in the other repo.** The "M-Pesa and bank" correction is in
`gigs-venture-docs` (`b49b754`), not here, because the creatives live in
`E:\Projects\Gigs`. The page and the ads now agree; see the cross-check below.

---

## Message match, page vs ads

Checked against the branch tip and the corrected creatives:

| | page | ads |
|---|---|---|
| hook | "annoying work" ×3 | all six creatives |
| the books | "M-Pesa and bank messages" | `lg-1c`, `lg-1e`, `lg-1f` corrected |
| core tool price | "from 8K" | "from KSh 8,000" |
| speed | "Live in a week" | "ONE WEEK" |
| number | 754 ×6 | 754 on every creative |
| Mercy's 716 | absent | absent |

---

## Left for Bonnie

1. **Merge the tip.** That is the publish.
2. **The clips.** Record them, then flip `data-clips` to `"on"`. Nothing else
   to change.
3. **`lg-1a` / `lg-1d`.** Their `M-PESA · OUT` is a worked example of one
   parsed message, not a scope claim, so they were not touched. If they
   undersell by only ever showing an M-Pesa sample, the fix is a KCB sample
   alongside, which is new artwork.
4. **Testimonial.** The Mercy quote in section 05 is attributed to a real
   person. Worth confirming she is happy for it to run in a paid campaign.
5. **Claims in section 05.** "30s to a price", "0 back-and-forth", "100% leads
   itemised" are stated as measured. Worth knowing what they are measured from
   before the ads drive traffic to them.

## Not done, deliberately

No Meta action, no ad launch, no publish. `main` untouched and releasable.
