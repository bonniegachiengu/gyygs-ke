#!/usr/bin/env node
/**
 * Run a Python script with the API's virtualenv interpreter.
 *
 * `npm run gen` used to call bare `python`, which on Windows resolved to the
 * system interpreter rather than apps/api/.venv — a different (older) FastAPI,
 * which failed at import with an unrelated assertion. Contract generation must
 * use the same interpreter the tests do, or the committed schema can drift from
 * the API that is actually running.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const repoRoot = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const venv = join(repoRoot, "apps", "api", ".venv");

const candidates = [
  join(venv, "Scripts", "python.exe"), // Windows
  join(venv, "bin", "python3"), // POSIX
  join(venv, "bin", "python"),
];

const python = candidates.find(existsSync);
if (!python) {
  console.error(
    "No virtualenv found at apps/api/.venv — create it first:\n" +
      "  cd apps/api && python -m venv .venv && .venv/Scripts/pip install -e \".[dev]\"",
  );
  process.exit(1);
}

const { status } = spawnSync(python, process.argv.slice(2), { stdio: "inherit" });
process.exit(status ?? 1);
