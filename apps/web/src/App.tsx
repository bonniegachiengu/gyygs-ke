import { useEffect, useState } from "react";

/**
 * M0 — the pipe. This page exists to prove one thing end to end: the browser can
 * reach the API through whatever is proxying `/api` (Vite in dev, nginx in prod,
 * Cloudflare Tunnel in production). It is replaced by the calculator in M1.
 */

type Health = { status: string; version: string };
type Probe =
  | { state: "loading" }
  | { state: "ok"; health: Health }
  | { state: "error"; message: string };

export default function App() {
  const [probe, setProbe] = useState<Probe>({ state: "loading" });

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/health", { signal: ac.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`API returned ${r.status}`);
        return (await r.json()) as Health;
      })
      .then((health) => setProbe({ state: "ok", health }))
      .catch((err: unknown) => {
        if (ac.signal.aborted) return;
        setProbe({ state: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => ac.abort();
  }, []);

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-6 p-6">
      <header>
        <p className="text-sm font-semibold tracking-widest text-green uppercase">
          Myra Cleaning Services
        </p>
        <h1 className="mt-1 text-3xl font-bold text-navy">Quote calculator</h1>
        <p className="mt-2 text-sm text-ink/70">
          v0 of gyygs.ke — deployment pipe check.
        </p>
      </header>

      <section
        className="rounded-[var(--radius-card)] bg-white p-5 shadow-sm ring-1 ring-navy/10"
        aria-live="polite"
      >
        <h2 className="text-xs font-semibold tracking-wider text-ink/50 uppercase">API health</h2>

        {probe.state === "loading" && <p className="mt-2 text-ink/60">Checking the API…</p>}

        {probe.state === "ok" && (
          <div className="mt-2">
            <p className="flex items-center gap-2 text-lg font-semibold text-green">
              <span aria-hidden="true">●</span> {probe.health.status}
            </p>
            <p className="mt-1 text-sm text-ink/60">API version {probe.health.version}</p>
          </div>
        )}

        {probe.state === "error" && (
          <div className="mt-2">
            <p className="text-lg font-semibold text-red-700">unreachable</p>
            <p className="mt-1 text-sm break-words text-ink/60">{probe.message}</p>
          </div>
        )}
      </section>
    </main>
  );
}
