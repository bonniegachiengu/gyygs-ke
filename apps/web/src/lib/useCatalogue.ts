/**
 * Loads GET /api/pricing once and keeps it.
 *
 * No TanStack Query: the whole app makes two calls, and Query would add ~12 kB
 * gzipped against QUOTE_CALCULATOR_SPEC §12's "keep the frontend lean".
 *
 * A cached copy in sessionStorage is served synchronously on load, so a returning
 * customer sees prices with zero network. Revalidation happens in the background;
 * if it fails, the cached catalogue keeps working (§9: slow/dropped data must
 * never block the flow).
 */

import { useEffect, useState } from "react";

import { api } from "./api/client";
import type { components } from "./api/schema";

export type Catalogue = components["schemas"]["PricingCatalogue"];

const CACHE_KEY = "myra.catalogue.v1";

function readCache(): Catalogue | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as Catalogue) : null;
  } catch {
    return null;
  }
}

function writeCache(cat: Catalogue): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cat));
  } catch {
    // Private mode or a full quota — the app works fine without the cache.
  }
}

let inflight: Promise<Catalogue> | null = null;

export function fetchCatalogue(): Promise<Catalogue> {
  // `??=` does not narrow the outer `let`, so assign to a local first.
  const pending =
    inflight ??
    api.GET("/api/pricing").then((result) => {
      if (!result.data) throw new Error(`pricing unavailable (${result.response.status})`);
      writeCache(result.data);
      return result.data;
    });
  inflight = pending;
  return pending;
}

export type CatalogueState = {
  catalogue: Catalogue | null;
  /** True only while there is nothing at all to show — a cached copy skips this. */
  loading: boolean;
  error: string | null;
  retry: () => void;
};

export function useCatalogue(): CatalogueState {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(readCache);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    fetchCatalogue()
      .then((cat) => {
        if (alive) {
          setCatalogue(cat);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        inflight = null; // let a retry actually retry
        if (!alive) return;
        // Only surface an error when there is nothing cached to fall back on.
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      alive = false;
    };
  }, [attempt]);

  return {
    catalogue,
    loading: catalogue === null && error === null,
    error: catalogue === null ? error : null,
    retry: () => {
      inflight = null;
      setError(null);
      setAttempt((n) => n + 1);
    },
  };
}
