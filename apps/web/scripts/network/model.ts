/**
 * A model of a distant client's link (owner ask 2026-10-21: load time must hold for a user in
 * India reaching the Mac behind Tailscale Funnel), for the throttled performance gate
 * (e2e/perf-network.spec.ts). It is arithmetic, not a measurement: one connection (TCP + TLS
 * cost two round trips before the first request), one round trip per request, TCP slow start
 * doubling the window each round trip until it covers the bandwidth-delay product, and one
 * shared downlink the responses queue on. Everything is in milliseconds on the test's clock.
 */

export interface Link {
  /** Round trip time, ms. */
  rttMs: number;
  /** Downlink, megabit per second. */
  downMbit: number;
}

/** The profile the gate runs: a client in India reaching a US Pacific host. */
export const DISTANT: Link = { rttMs: 280, downMbit: 10 };

const INITIAL_WINDOW_BYTES = 10 * 1460;

export class LinkModel {
  private connected = false;
  private window = INITIAL_WINDOW_BYTES;
  private linkFree = 0;

  constructor(private readonly link: Link) {}

  /**
   * When a response of `bytes` (on the wire) requested at `nowMs` is complete: the delay from
   * `nowMs`. Call in request order; the model keeps the connection's window and the link's queue.
   */
  delay(nowMs: number, bytes: number): number {
    const { rttMs, downMbit } = this.link;
    let t = nowMs;
    if (!this.connected) {
      this.connected = true;
      t += 2 * rttMs;
    }
    t += rttMs; // the request out, the first byte back
    const bytesPerMs = (downMbit * 1_000_000) / 8 / 1000;
    const bdp = bytesPerMs * rttMs;
    let sent = 0;
    while (sent + this.window < bytes && this.window < bdp) {
      sent += this.window;
      this.window *= 2;
      t += rttMs; // one more window flight
    }
    const start = Math.max(t, this.linkFree);
    this.linkFree = start + bytes / bytesPerMs;
    return this.linkFree - nowMs;
  }
}

export interface Span {
  start: number;
  end: number;
  /** What it was, for the waterfall `PERF_TRACE=1` prints. */
  label?: string;
}

/**
 * The serial round-trip depth of a load: a request's level is one more than the deepest request
 * that had finished when it started (it could not start earlier, so it waited for that one).
 */
export function roundTripDepth(spans: readonly Span[]): number {
  const ordered = [...spans].sort((a, b) => a.start - b.start);
  const levels: number[] = [];
  let deepest = 0;
  ordered.forEach((span, i) => {
    let level = 1;
    ordered.slice(0, i).forEach((other, j) => {
      if (other.end <= span.start) level = Math.max(level, (levels[j] ?? 1) + 1);
    });
    levels.push(level);
    deepest = Math.max(deepest, level);
  });
  return deepest;
}
