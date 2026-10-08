/**
 * The Guide end to end, against the production build with the API mocked (explore-api.ts): the
 * top bar's Guide link and the "?" key, the home with its theme groups, the field index, a
 * field's page (what it means, its spread, criteria, when it lies, related, a ticker), the rail's
 * search, the playbook and situation pages reached from the home (a linked field and back, the two
 * buttons, the linked prose), the market regime pages (the index, an indicator, an episode), and Explore's retired Field guide tab redirecting here; accessible
 * in dark and light.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';

const IV30 = 'rollup.iv30@v1.iv30';
const SITUATION_NAME = 'Earnings gap inside the window';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('the top bar links to the Guide, and "?" opens it', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await page.getByRole('link', { name: /^Guide/ }).click();
  await expect(page).toHaveURL(/\/guide$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Guide' })).toBeVisible();
  await page.goto('/explore');
  // The shortcut listener mounts with the layout, and "?" inside a text field is a character
  // (use-guide-shortcut.ts): wait for the page, then make sure nothing has the focus.
  await expect(page.getByRole('link', { name: /^Guide/ })).toBeVisible();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press('?');
  await expect(page).toHaveURL(/\/guide$/);
  expect(errors).toEqual([]);
});

test('an admin who opens the Guide from ADMIN stays in ADMIN, and the switch still works', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/admin/ingestion');
  await expect(page.getByRole('link', { name: 'Ingestion' })).toBeVisible();
  await page.getByRole('link', { name: /^Guide/ }).click();
  await expect(page).toHaveURL(/\/guide$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Guide' })).toBeVisible();
  // Still ADMIN: its sections in the bar, its radio checked in the account menu.
  await expect(page.getByRole('link', { name: 'Ingestion' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ideas' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Abhi Admin' }).click();
  await expect(page.getByRole('radio', { name: 'Admin' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('radio', { name: 'Trader' }).click();
  await expect(page).toHaveURL(/\/ideas$/);
  expect(errors).toEqual([]);
});

for (const theme of ['dark', 'light'] as const) {
  test(`home to a field page: its meaning, spread, criteria and caveats (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/guide');
    await expect(page.getByRole('heading', { level: 2, name: 'Fields' })).toBeVisible();
    // Sections of later phases are not shown yet.
    await expect(page.getByRole('link', { name: 'Start here' })).toHaveCount(0);
    await page.getByRole('link', { name: /^Implied volatility · / }).click();
    await expect(page).toHaveURL(/\/guide\/fields\?theme=implied/);
    await page.getByRole('link', { name: IV30 }).first().click();
    await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30/);

    const hero = page.getByRole('region', { name: 'What this field means' });
    await expect(hero.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(hero).toContainText('30-day at-the-money implied volatility');
    await expect(hero).toContainText('names have a value today');

    const universe = page.getByRole('region', { name: 'Across the universe today' });
    await expect(universe.getByRole('img')).toBeVisible();
    await expect(universe).toContainText(/[\d,]+ names pass “Rich premium to sell” today/);

    const use = page.getByRole('region', { name: 'Use it for' });
    await expect(use).toContainText('gte 0.4 soft tolerance 0.05');
    await expect(use.getByRole('button', { name: 'Add to Builder' })).toHaveCount(2);

    await expect(page.locator('#lies').getByText('When it lies')).toBeVisible();
    await expect(page.getByText('Earnings gap inside the window')).toBeVisible();
    const related = page.getByRole('region', { name: 'Related fields and playbooks' });
    await expect(related.getByRole('link', { name: 'feature.iv_hv_ratio' })).toBeVisible();
    await expect(related).toContainText('VRP scanner');

    await page
      .getByRole('navigation', { name: 'On this page' })
      .getByRole('link', { name: 'Use it for' })
      .click();
    await expect(page).toHaveURL(/#use$/);

    const ticker = page.getByRole('region', { name: 'See it on a ticker' });
    await ticker.getByRole('textbox', { name: 'Symbol' }).fill('aapl');
    await ticker.getByRole('textbox', { name: 'Symbol' }).press('Enter');
    await expect(
      ticker.getByRole('img', { name: /shaded value zone: Rich premium to sell/ }),
    ).toBeVisible();

    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);

    await ticker.getByRole('link', { name: 'Open in Explore with its history' }).click();
    await expect(page).toHaveURL(/\/explore\?.*tab=features/);
    expect(errors).toEqual([]);
  });
}

for (const theme of ['dark', 'light'] as const) {
  test(`home to a playbook, a linked field and back (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/guide');
    await expect(page.getByRole('heading', { level: 2, name: 'Playbooks' })).toBeVisible();
    await page
      .getByRole('region', { name: 'Option income' })
      .getByRole('link', { name: 'VRP scanner' })
      .click();
    await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
    await expect(page.getByRole('heading', { level: 1, name: 'VRP scanner' })).toBeVisible();
    await expect(page.getByText('site preset · vrp_scanner v1 · Option income')).toBeVisible();
    await expect(page.getByText('Finds names whose options price more movement')).toBeVisible();

    const criteria = page.getByRole('grid', { name: 'VRP scanner criteria' });
    await expect(criteria.getByRole('row', { name: /Implied volatility is rich/ })).toContainText(
      'gte 0.4 soft tolerance 0.05',
    );
    // The caveat names a field: a link to its page.
    const before = page.getByRole('region', { name: 'Before you act on a hit' });
    await expect(before.getByRole('link', { name: IV30 })).toBeVisible();
    await expect(before.getByRole('link', { name: SITUATION_NAME })).toBeVisible();

    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);

    await criteria.getByRole('link', { name: IV30 }).click();
    await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30$/);
    await expect(page.getByRole('region', { name: 'What this field means' })).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
    await expect(page.getByRole('heading', { level: 1, name: 'VRP scanner' })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('a playbook opens today’s hits and its Builder; the index lists the families', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/guide/playbooks');
  await expect(page.getByRole('region', { name: 'Breakouts' })).toContainText('Finds shares');
  await page.getByRole('link', { name: 'VRP scanner' }).first().click();
  await page.getByRole('button', { name: 'See today’s hits' }).click();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner$/);
  await page.goto('/guide/playbooks/vrp_scanner');
  await page.getByRole('button', { name: 'Open in Builder' }).click();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner\/edit$/);
  await page.goto('/guide/playbooks/nope');
  await expect(page.getByText('No such playbook')).toBeVisible();
  expect(errors).toEqual([]);
});

test('situations: the index, a situation’s page with its linked fields and playbooks', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/guide/situations');
  await page.getByRole('link', { name: SITUATION_NAME }).first().click();
  await expect(page).toHaveURL(/\/guide\/situations\/earnings-gap-inside-the-window$/);
  await expect(page.getByRole('heading', { level: 1, name: SITUATION_NAME })).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'What to do' }).getByRole('link', { name: IV30 }),
  ).toBeVisible();
  await page
    .getByRole('region', { name: 'Playbooks it affects' })
    .getByRole('link', { name: 'VRP scanner' })
    .click();
  await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
  await page.goto('/guide/situations/nope');
  await expect(page.getByText('No such situation')).toBeVisible();
  expect(errors).toEqual([]);
});

test('a field page links its caveats’ fields, its situations and its playbooks', async ({
  page,
}) => {
  await page.goto(`/guide/fields/${IV30}`);
  const lies = page.locator('#lies');
  await expect(lies.getByRole('link', { name: SITUATION_NAME })).toHaveAttribute(
    'href',
    '/guide/situations/earnings-gap-inside-the-window',
  );
  await page
    .getByRole('region', { name: 'Related fields and playbooks' })
    .getByRole('link', { name: 'VRP scanner' })
    .click();
  await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
});

test('the rail searches the fields and the index has three views', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/guide/fields');
  await page.getByRole('searchbox', { name: 'Search the guide' }).fill('realised');
  const results = page.getByRole('navigation', { name: 'Search results' });
  await expect(results.getByRole('link', { name: 'rollup.price_stats@v2.hv30' })).toBeVisible();
  await expect(results.getByRole('link', { name: IV30 })).toHaveCount(0);
  await page.getByRole('searchbox', { name: 'Search the guide' }).fill('zzzz');
  await expect(page.getByText('No field matches “zzzz”.')).toBeVisible();
  await page.getByRole('radio', { name: 'By intent' }).click();
  await expect(page).toHaveURL(/view=intent/);
  await page.getByRole('link', { name: /^Cheap options to buy/ }).click();
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  await page.goto('/guide/fields?view=az');
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  expect(errors).toEqual([]);
});

test('an unknown field says so instead of loading for good', async ({ page }) => {
  await page.goto('/guide/fields/feature.nope');
  await expect(page.getByText('No such field')).toBeVisible();
});

test('the Explore Field guide tab redirects to the Guide, keeping the field', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?sel=AAPL');
  await page.getByRole('tab', { name: 'Field guide' }).click();
  await expect(page).toHaveURL(/\/guide\/fields$/);
  await page.goto(`/explore?tab=guide&field=${IV30}&symbol=AAPL`);
  await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30$/);
  await page.goto('/explore?tab=guide&theme=volatility');
  await expect(page).toHaveURL(/\/guide\/fields\?theme=volatility$/);
  expect(errors).toEqual([]);
});

for (const theme of ['dark', 'light'] as const) {
  test(`market regime: the index to an indicator to an episode and back (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/guide');
    await expect(page.getByRole('heading', { level: 2, name: 'Market regime' })).toBeVisible();
    await page
      .getByRole('region', { name: 'Market regime' })
      .getByRole('link', { name: 'The warning signs and the falls' })
      .click();
    await expect(page).toHaveURL(/\/guide\/regime$/);
    const slow = page.getByRole('region', { name: 'Slow-moving warning signs' });
    await expect(slow.getByRole('link')).toHaveCount(5);
    await expect(
      page.getByRole('region', { name: 'Fast-moving market signs' }).getByRole('link'),
    ).toHaveCount(3);
    await expect(
      page.getByRole('link', { name: 'Today’s readings on the Regime page' }),
    ).toHaveAttribute('href', '/regime');

    await slow.getByRole('link', { name: 'Are long-term rates below short-term ones?' }).click();
    await expect(page).toHaveURL(/\/guide\/regime\/indicators\/curve_10y3m$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Are long-term rates below short-term ones?' }),
    ).toBeVisible();
    await expect(page.getByRole('region', { name: 'Why it matters' })).toContainText(
      'Normally lenders want more to lend for longer',
    );
    await expect(page.getByRole('region', { name: 'Lead time and track record' })).toContainText(
      '6 to 18 months before a recession.',
    );
    await expect(
      page
        .getByRole('region', { name: 'Sources' })
        .getByRole('link', { name: /FRED: 10-year/ })
        .first(),
    ).toBeVisible();
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);

    await page
      .getByRole('region', { name: 'What it did before' })
      .getByRole('link', { name: '2008' })
      .click();
    await expect(page).toHaveURL(/\/guide\/regime\/episodes\/gfc_2007$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Global financial crisis, 2007-09' }),
    ).toBeVisible();
    await expect(page.getByText('The housing bust and subprime losses')).toBeVisible();
    await expect(page.getByRole('region', { name: 'The fall' })).toContainText('Recovered');
    await expectAccessible(page);

    await page
      .getByRole('region', { name: 'What the warning signs did before it' })
      .getByRole('link', { name: 'Are long-term rates below short-term ones?' })
      .click();
    await expect(page).toHaveURL(/\/guide\/regime\/indicators\/curve_10y3m$/);
    expect(errors).toEqual([]);
  });
}

test('an unknown indicator or market fall says so', async ({ page }) => {
  await page.goto('/guide/regime/indicators/nope');
  await expect(page.getByText('No such indicator')).toBeVisible();
  await page.goto('/guide/regime/episodes/nope');
  await expect(page.getByText('No such market fall')).toBeVisible();
});
