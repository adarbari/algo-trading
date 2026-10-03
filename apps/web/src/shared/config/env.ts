/** Build-time configuration read from Vite env (`VITE_*`): the one place app code reads env. */

/** Base URL of the API. Default `/api` on the same origin (the dev server proxies it to the API). */
export const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '/api';
