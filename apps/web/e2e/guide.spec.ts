/**
 * The Guide end to end, against the production build with the API mocked (explore-api.ts): the
 * top bar's Guide link and the "?" key, the home with its theme groups, the field index, a
 * field's page (what it means, its spread, criteria, when it lies, related, a ticker), the Start here
 * steps, the glossary and the search dialog (Ctrl+K and the rail's button), the playbook and situation pages reached from the home (a linked field and back, the two
 * buttons, the linked prose), and the market regime pages (the index, an indicator, an episode);
 * accessible in dark and light.
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

test('the field index has three views', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/guide/fields');
  await page.getByRole('radio', { name: 'By intent' }).click();
  await expect(page).toHaveURL(/view=intent/);
  await page.getByRole('link', { name: /^Cheap options to buy/ }).click();
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  await page.goto('/guide/fields?view=az');
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  expect(errors).toEqual([]);
});

test('the home lists Start here first and the Glossary last, and the rail follows that order', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/guide');
  await expect(page.getByRole('heading', { level: 2 })).toHaveText([
    'Start here',
    'Market regime',
    'Playbooks',
    'Fields',
    'Situations',
    'Glossary',
  ]);
  const rail = page.getByRole('navigation', { name: 'Guide' });
  await expect(rail.getByRole('link').first()).toHaveText('Overview');
  await expect(rail.getByRole('link', { name: /^Start here/ })).toBeVisible();
  await expect(rail.getByRole('link', { name: /^Glossary/ })).toBeVisible();
  expect(errors).toEqual([]);
});

test('Start here: the steps in order, a page with its links, and the next step', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/guide/start');
  const steps = page.getByRole('list', { name: /reading order/ });
  await expect(steps.getByRole('listitem')).toHaveText([
    /^1\s*How the app thinks about a day/,
    /^2\s*Read a screen result/,
  ]);
  await steps.getByRole('link', { name: 'How the app thinks about a day' }).click();
  await expect(page).toHaveURL(/\/guide\/start\/how_the_app_thinks$/);
  await expect(page.getByText('Start here · step 1')).toBeVisible();
  await expect(page.getByRole('region', { name: 'One session' })).toBeVisible();
  await page
    .getByRole('region', { name: 'Where to look next' })
    .getByRole('link', { name: 'UNKNOWN' })
    .click();
  await expect(page).toHaveURL(/\/guide\/glossary\/unknown$/);
  await page.goto('/guide/start/how_the_app_thinks');
  await page.getByRole('navigation', { name: 'Next page' }).getByRole('link').click();
  await expect(page).toHaveURL(/\/guide\/start\/read_a_result$/);
  await page.goto('/guide/start/nope');
  await expect(page.getByText('No such page')).toBeVisible();
  expect(errors).toEqual([]);
});

for (const theme of ['dark', 'light'] as const) {
  test(`Glossary: A to Z to a term and the terms it sends you to (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/guide/glossary');
    await expect(page.getByRole('heading', { level: 2 })).toHaveText(['N', 'S', 'U']);
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);
    await page
      .getByRole('region', { name: 'Terms starting with S' })
      .getByRole('link', { name: 'Session' })
      .click();
    await expect(page).toHaveURL(/\/guide\/glossary\/session$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Session' })).toBeVisible();
    await expect(page.getByText('The trading day a page is reading.')).toBeVisible();
    await page
      .getByRole('region', { name: 'See also' })
      .getByRole('link', { name: 'UNKNOWN' })
      .click();
    await expect(page).toHaveURL(/\/guide\/glossary\/unknown$/);
    await expectAccessible(page);
    await page.goto('/guide/glossary/nope');
    await expect(page.getByText('No such term')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('search: Ctrl+K from any page, type, Enter lands on the entry; the rail button opens it too', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await expect(page.getByRole('link', { name: /^Guide/ })).toBeVisible();
  await page.keyboard.press('ControlOrMeta+k');
  const dialog = page.getByRole('dialog', { name: 'Search the Guide' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('searchbox').fill('session');
  await expect(dialog.getByRole('region', { name: 'Glossary' })).toBeVisible();
  await expect(dialog.getByRole('region', { name: 'Start here' })).toBeVisible();
  await page.keyboard.press('Enter');
  // The first result is the Start here page that mentions the word, the groups in the server's order.
  await expect(page).toHaveURL(/\/guide\/start\/how_the_app_thinks$/);
  await expect(dialog).toHaveCount(0);

  // On a Guide page the rail's button opens the same dialog; arrows walk the results.
  await page.getByRole('button', { name: 'Search the Guide' }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole('searchbox').fill('implied');
  await expect(dialog.getByRole('region', { name: 'Fields' })).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await expect(dialog.getByRole('link', { name: IV30 })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30$/);

  await page.keyboard.press('ControlOrMeta+k');
  await dialog.getByRole('searchbox').fill('zzzz');
  await expect(dialog.getByText('Nothing matches “zzzz”.')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('an unknown field says so instead of loading for good', async ({ page }) => {
  await page.goto('/guide/fields/feature.nope');
  await expect(page.getByText('No such field')).toBeVisible();
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
