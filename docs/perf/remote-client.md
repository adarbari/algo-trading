# Loading well for a distant client

Owner ask 2026-10-21: a user in India (RTT 250-300 ms) reaching the Mac behind Tailscale Funnel.
Nothing here was measured from another continent; the gate is a model (`docs/ci.md` "Web performance").

## Done (PR #771) and next
- Gate: `apps/web/e2e/perf-network.spec.ts`, budgets `network` in `perf-budgets.json`.
- index.html preloads the opened path's page files, page cache and fonts; a trader page's reads start at start-up beside the Viewer. Modelled: one round trip less on Ideas and Edges.
- Measured on a spare API (loaded machine): IdeasPage 4.7 MB raw is 339 kB gzip on the wire. At 10 Mbit that is about 0.3 s of transfer plus slow-start rounds; the real cost is server time and the JSON parse. Next: window and project the Ideas payload (add-graphql-field; ADR 0036-0038), after the serving-release `config_generation` contract lands.
- Later, once it lands: the client invalidates its page cache by `config_generation` after a write.

## Owner decisions (not implemented)
1. **CDN in front.** Needs the owner's own domain: a `.ts.net` Funnel hostname cannot be fronted. Hashed assets are immutable, so a CDN would serve the whole shell from near the user; only GraphQL would cross the ocean. Biggest remaining win for a distant client.
2. **Funnel uplink.** A hairpin test gave about 1.2 MB/s. Every uncached byte (JS on a first visit, the Ideas JSON) shares the Mac's uplink. Options: CDN (above), or a cheap VPS reverse proxy that caches static files.
3. **HTTP/3.** Funnel's edge decides; we cannot enable it. QUIC would cut connection setup from 2 round trips to 1 (0 on repeat) and avoid head-of-line blocking on loss, which matters at 250 ms. Check what Funnel negotiates before relying on it.
4. **Real measurement from India** (WebPageTest Mumbai) needs sending the private URL to a third party: not done, needs the owner's say.
5. **Service worker / shell cache:** not built. Repeat visits already hit immutable assets; a worker could serve index.html stale and so a stale auth state. Revisit only if the gate shows a win that the page cache does not already give.
