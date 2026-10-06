/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the API (default `/api`, same origin). */
  readonly VITE_API_BASE_URL?: string;
  /** The Supabase project URL (sign-in, ADR 0040); unset when the API runs with auth off. */
  readonly VITE_SUPABASE_URL?: string;
  /** The Supabase project's anon key. */
  readonly VITE_SUPABASE_ANON_KEY?: string;
}
