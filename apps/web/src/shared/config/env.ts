/** Build-time configuration read from Vite env (`VITE_*`): the one place app code reads env. */

/** Base URL of the API. Default `/api` on the same origin (the dev server proxies it to the API). */
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '/api';

/** The Supabase project URL (ADR 0040): unset when the API runs with `ALGOTRADE_AUTH=off`. */
export const supabaseUrl: string | undefined = import.meta.env.VITE_SUPABASE_URL;

/** The Supabase project's public anon key (safe in the browser; row access is not used). */
export const supabaseAnonKey: string | undefined = import.meta.env.VITE_SUPABASE_ANON_KEY;
