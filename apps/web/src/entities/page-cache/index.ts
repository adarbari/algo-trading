/**
 * Entity: the page cache kept between visits (owner decision 2026-10-09). `startQueryPersistence`
 * saves the query cache's GraphQL page reads to IndexedDB (10 MB cap, least recently used out
 * first), restores them once the API's session date matches the saved one, and forgets them on
 * sign-out. Only a trader page's chunk imports this, dynamically, so none of it is in the entry chunk.
 */
export { startQueryPersistence } from './api/query-persistence';
