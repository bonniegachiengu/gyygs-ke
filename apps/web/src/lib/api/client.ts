import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/**
 * The only place this app calls `fetch`.
 *
 * `baseUrl: ""` means every request is same-origin. The API is mounted under
 * `/api`, and both the Vite dev proxy and nginx forward that prefix — so there
 * is no build-time API base URL that can be wrong in one environment and right
 * in another, and the web image is environment-independent.
 *
 * Types come from `schema.d.ts`, which is GENERATED from the FastAPI OpenAPI
 * document (`npm run gen`). A backend contract change becomes a compile error
 * here rather than a runtime surprise on a customer's phone.
 */
export const api = createClient<paths>({ baseUrl: "" });

/** Response shapes, named off the generated component schemas. */
export type Health = components["schemas"]["HealthResponse"];
