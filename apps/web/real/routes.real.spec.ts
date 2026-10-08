/**
 * "Real app" smoke: every route of both workspaces, opened in a browser against the real API
 * (empty store and golden fixture store; playwright.real.config.ts). A page fails when it logs a
 * console or page error, shows the Vite error overlay (a broken import, a stale node_modules),
 * or still shows a loading state after 10 s (a query that never settles: data, empty or error).
 */
import { expect, test, type Page } from '@playwright/test';

import { WORKSPACES } from '../src/app/workspaces/workspaces';

/**
 * Routes with a parameter or no top-bar section, opened with a plausible id; `/explore?sel=BULL`
 * opens one ticker's Overview, read over GraphQL (`POST /graphql`) from the real API.
 */
const EXTRA_ROUTES = [
  '/screeners/new',
  '/screeners/vrp_scanner/edit',
  '/explore?sel=BULL',
  '/guide',
  '/guide/start',
  '/guide/start/how_the_app_thinks',
  '/guide/glossary',
  '/guide/glossary/session',
  '/guide/fields',
  '/guide/playbooks',
  '/guide/playbooks/breakout',
  '/guide/situations',
  '/guide/situations/pending-takeover',
  '/guide/regime',
  '/guide/regime/indicators/curve_10y3m',
  '/guide/regime/episodes/gfc_2007',
];
const ROUTES = [...WORKSPACES.flatMap((w) => w.sections.map((s) => s.path)), ...EXTRA_ROUTES];

const SETTLE_MS = 10_000;

const NOT_FOUND_LOG = /^Failed to load resource: .*404/;

/**
 * Collects what a page must not do. The API answers 404 `{"detail": ...}` for "nothing stored
 * (yet)", which the pages show as an empty or error panel and the browser logs as one console
 * line each: those pairs are expected (an empty store has little to show). Any other failed
 * response (5xx, a 404 without a detail: a missing route or a dead proxy), console error or
 * page error is reported.
 */
function watch(page: Page): () => Promise<string[]> {
  const errors: string[] = [];
  const pending: Promise<void>[] = [];
  let notStored = 0;
  let notFoundLogs = 0;
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('response', (res) => {
    if (res.status() < 400) return;
    pending.push(
      res.text().then((body) => {
        if (res.status() === 404 && /"detail"\s*:/.test(body)) notStored += 1;
        else errors.push(`http ${String(res.status())}: ${res.url()} ${body}`);
      }),
    );
  });
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    if (NOT_FOUND_LOG.test(msg.text())) notFoundLogs += 1;
    else errors.push(`console: ${msg.text()}`);
  });
  return async () => {
    await Promise.all(pending);
    if (notFoundLogs > notStored)
      errors.push(`${String(notFoundLogs - notStored)} unexplained 404s`);
    return errors;
  };
}

for (const route of ROUTES) {
  test(`${route} loads, settles and logs no errors`, async ({ page }) => {
    const errors = watch(page);
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({
      timeout: SETTLE_MS,
    });
    await expect(page.locator('vite-error-overlay')).toHaveCount(0);
    // Every query ends in data, empty or error: nothing is still busy or "Loading…".
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: SETTLE_MS });
    await expect(page.getByText(/^Loading/)).toHaveCount(0, { timeout: SETTLE_MS });
    await expect(page.locator('vite-error-overlay')).toHaveCount(0);
    if (route === '/ideas') {
      // First run (no screener has run): an explained empty state, not a failure panel.
      await expect(page.getByText('The ideas failed to load.')).toHaveCount(0);
      await expect(page.getByText('The screeners failed to load.')).toHaveCount(0);
    }
    expect(await errors()).toEqual([]);
  });
}
