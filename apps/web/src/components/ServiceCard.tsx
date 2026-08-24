import { useId, useState } from "react";

import { serviceDetail } from "../lib/serviceDetails";

/**
 * A service card with two INDEPENDENT controls, which is the whole point:
 *
 *   - tapping the card BODY expands an explanation of what the service covers
 *     and how it is priced
 *   - the CHECKBOX on the right selects it
 *
 * Ticking must NOT open the accordion. A returning client who already knows
 * what "Sofa" means ticks the box and moves on; making the panel spring open
 * every time punishes the person who needs the least help.
 *
 * WHY A CHECKBOX AND NOT A RADIO: this page is multi-select — "pick everything
 * you need". A radio is the universal signal for "one of these", so using one
 * here would actively tell clients the opposite of what the page does.
 *
 * MARKUP NOTE: the body is a <button> and the checkbox is a real <input>, kept
 * as SIBLINGS inside a plain <div>. Nesting one interactive element inside
 * another is invalid HTML and breaks keyboard and screen-reader behaviour, so
 * the card itself is deliberately not a button.
 */
export function ServiceCard({
  serviceKey,
  selected,
  icon,
  title,
  hint,
  onToggleSelect,
}: {
  serviceKey: string;
  selected: boolean;
  icon?: string | null;
  title: string;
  hint?: string;
  onToggleSelect: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const boxId = useId();
  const detail = serviceDetail(serviceKey);

  return (
    <div
      className={[
        "overflow-hidden rounded-[var(--radius-card)] bg-white transition-colors",
        // Selected state must be obvious while COLLAPSED — that is the state
        // the client scans down the page, not the expanded one.
        selected
          ? "ring-2 ring-green shadow-[0_1px_0_0_rgba(0,0,0,0.02)]"
          : "ring-1 ring-navy/10",
      ].join(" ")}
    >
      <div className="flex items-stretch">
        {/* ── card body: expands the explanation ── */}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={detail ? panelId : undefined}
          className="flex min-h-[3.75rem] flex-1 items-center gap-3 p-4 text-left"
        >
          {icon && (
            <span className="text-2xl" aria-hidden="true">
              {icon}
            </span>
          )}
          <span className="flex-1">
            <span className="block font-semibold text-navy">{title}</span>
            <span className="flex items-center gap-1.5">
              {hint && <span className="text-sm text-ink/60">{hint}</span>}
              {detail && (
                <>
                  {hint && <span className="text-ink/25" aria-hidden="true">·</span>}
                  {/* The discoverability cue. Without it nothing suggests the
                      card does anything when tapped. */}
                  <span className="text-sm text-green/90">
                    {open ? "Hide details" : "Details"}
                  </span>
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    className={[
                      "h-4 w-4 text-green/70 transition-transform duration-200",
                      open ? "rotate-180" : "",
                    ].join(" ")}
                  >
                    <path
                      d="M5 7.5 10 12.5 15 7.5"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </>
              )}
            </span>
          </span>
        </button>

        {/* ── select control: thumb-sized, on the right, visually separated ── */}
        <label
          htmlFor={boxId}
          onClick={(e) => e.stopPropagation()}
          className={[
            "flex w-[4.25rem] shrink-0 cursor-pointer flex-col items-center justify-center gap-1",
            "border-l transition-colors",
            selected ? "border-green/30 bg-green/5" : "border-navy/10",
          ].join(" ")}
        >
          <input
            id={boxId}
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="sr-only"
          />
          {/* 28px box inside a 68px-wide, full-height target — comfortably past
              the ~44px minimum for a thumb. */}
          <span
            aria-hidden="true"
            className={[
              "flex h-7 w-7 items-center justify-center rounded-md transition-colors",
              selected
                ? "bg-green text-white"
                : "bg-white ring-2 ring-navy/20",
            ].join(" ")}
          >
            {selected && (
              <svg viewBox="0 0 20 20" className="h-5 w-5">
                <path
                  d="M5 10.5 8.5 14 15 6.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </span>
          <span
            className={[
              "text-[0.65rem] font-medium",
              selected ? "text-green" : "text-ink/45",
            ].join(" ")}
          >
            {selected ? "Added" : "Add"}
          </span>
        </label>
      </div>

      {/* ── the explanation ── */}
      {detail && open && (
        <div
          id={panelId}
          className="border-t border-navy/10 bg-navy/[0.02] px-4 py-3 text-sm leading-relaxed text-ink/75"
        >
          <p>{detail.includes}</p>
          <p className="mt-2">
            <span className="font-medium text-navy/80">How it&apos;s priced: </span>
            {detail.priced}
          </p>
          {detail.note && (
            <p className="mt-2 text-ink/60">{detail.note}</p>
          )}
        </div>
      )}
    </div>
  );
}
