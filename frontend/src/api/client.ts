import createClient from "openapi-fetch";

import type { paths } from "./schema";

// The dev proxy and the nginx image both put the API under /api on this origin, so there is
// no base URL to configure and no environment variable that can be wrong at build time.
export const api = createClient<paths>({ baseUrl: "/api" });

type Json<T> = T extends { content: { "application/json": infer B } } ? B : never;

export type SearchResponse = Json<paths["/search"]["post"]["responses"][200]>;

export type Hit = SearchResponse["hits"][number];
export type Interpretation = SearchResponse["interpretation"];
