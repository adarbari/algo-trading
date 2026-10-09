/**
 * The page cache kept between visits (owner decision 2026-10-09): `warmPage` for a trader page's
 * chunk (that page's read, and the saved cache started once); the saved cache itself
 * (query-persistence.ts, persist-cap.ts) loads lazily behind it.
 */
export { warmPage } from './warm';
