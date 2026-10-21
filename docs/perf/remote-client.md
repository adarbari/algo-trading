# Loading well for a distant client

Owner ask 2026-10-21: a user in India (RTT 250-300 ms) reaching the Mac behind Tailscale Funnel.
Nothing here was measured from another continent; the gate is a model (`docs/ci.md` "Web performance").

## Done (PR #771) and next
- Gate: `apps/web/e2e/perf-network.spec.ts`, budgets `network` in `perf-budgets.json`.
- index.html preloads the opened path's page files, page cache and fonts (modelled: Ideas and Edges lose one round trip).
- **Held back, needs an owner decision:** starting a trader page's reads at start-up beside the Viewer (not after it) saves about one more round trip of data time (the model's Ideas data lands at 2.08 s instead of about 2.35 s). It needs a lazy chunk imported from index.html; the one-line import in the entry costs about 90 B gzip and the entry's static-imports budget has about 35 B of margin, so it needs an owner waiver of that shared budget (docs/ci.md budget policy). The code and tests are kept in the shared notes folder (`early-reads/`), reviewed by the architect (the in-flight read must survive the page cache's reconcile, which PR #771 now guarantees).
- Measured on a spare API (2026-10-21, one request): IdeasPage is 4.8 MB raw, 339 kB gzip on the wire, for 200 of 9434 ideas. **88% of the gzip bytes are `picks`** (284 of 321 kB): 34 picks per idea on average (one per screener), each with `columns` (151 kB gz) and `criteria` (116 kB gz). Feature values (15 kB gz, the repeated `info` only 2 kB gz), `screeners` (6 kB) and the rest are small. So a client-only cut cannot help: the table needs every idea's best pick, the page filters over all 200, and `picks` has no argument to window it.
- Proposal for the next PR (API + web, add-graphql-field, ADR 0036-0038; touches `services/read/screens/ideas.py`, where the API-memory session works, so coordinate first): serve the list with each idea's best pick plus a summary of the others (decision, score, outcomes), and the full `picks` of one ticker on demand when its row opens (a second operation on the Explore side). Expected: about 20-40 kB gz for the list. A smaller `limit` is the cheap alternative but changes what the chips filter over: an owner decision.
- Later, once it lands: the client invalidates its page cache by `config_generation` after a write.

## Owner decisions (not implemented)
1. **CDN in front.** Needs the owner's own domain: a `.ts.net` Funnel hostname cannot be fronted. Hashed assets are immutable, so a CDN would serve the whole shell from near the user; only GraphQL would cross the ocean. Biggest remaining win for a distant client.
2. **Funnel uplink.** A hairpin test gave about 1.2 MB/s. Every uncached byte (JS on a first visit, the Ideas JSON) shares the Mac's uplink. Options: CDN (above), or a cheap VPS reverse proxy that caches static files.
3. **HTTP/3.** Funnel's edge decides; we cannot enable it. QUIC would cut connection setup from 2 round trips to 1 (0 on repeat) and avoid head-of-line blocking on loss, which matters at 250 ms. Check what Funnel negotiates before relying on it.
4. **Real measurement from India** (WebPageTest Mumbai) needs sending the private URL to a third party: not done, needs the owner's say.
5. **Service worker / shell cache:** not built. Repeat visits already hit immutable assets; a worker could serve index.html stale and so a stale auth state. Revisit only if the gate shows a win that the page cache does not already give.
