/**
 * Trader > Edges end to end, against the production build with the edges mocked (edges-api.ts):
 * the list shows each edge under its verdict, the chosen edge's page shows the verdict, what would
 * change it, its sections in order (the evidence curve, how sure, where it worked, the definition)
 * each loaded as it is reached, the out-of-sample figures and the details (an exploratory run is labelled and never shown as
 * figures), the chosen edge lives in the URL, and the six-step builder (clone, edit a screen in the
 * Screen Builder and return, save the whole edge, run the backtest); the Screeners list shows a track-record chip and Ideas an odds line for a
 * screener a candidate edge lists.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockEdgesApi } from './edges-api';
import { mockApi } from './mock-api';

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

test('the Edges tab lists the edges and the chosen edge shows its verdict and figures', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await page.getByRole('navigation', { name: 'Trader sections' }).getByText('Edges').click();
  await expect(page).toHaveURL(/\/edges$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Edges' })).toBeVisible();
  const list = page.getByRole('grid', { name: 'Edges' });
  await expect(list.getByRole('row', { name: /Momentum 12-1/ })).toContainText('Promising');
  await expect(list.getByRole('row', { name: /S&P 500 index changes/ })).toContainText(
    'Waiting on data',
  );
  await list.getByRole('row', { name: /Momentum 12-1/ }).click();
  await expect(page).toHaveURL(/\/edges\?edge=momentum_12_1$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeVisible();
  await expect(page.getByText('+7.0 pts').first()).toBeVisible();
  // The evaluation line under the verdict: the server's state and sentence, and no run id for a trader.
  await expect(page.getByText('Stale', { exact: true })).toBeVisible();
  await expect(page.getByText(/^Evaluated 2 Oct, 8 sessions ago\./)).toBeVisible();
  await expect(page.getByRole('link', { name: /run-frozen/ })).toHaveCount(0);
  await page
    .getByRole('navigation', { name: 'Sections of this edge' })
    .getByRole('link', { name: 'Details' })
    .click();
  await page.getByRole('button', { name: /^Details/ }).click();
  await page.getByRole('heading', { level: 3, name: 'Variants tried' }).scrollIntoViewIfNeeded();
  await expect(page.getByText('EXPLORATORY')).toBeVisible();
  await expect(page.getByText('99.0%')).toHaveCount(0);
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test("the chosen edge's page reads in order: the verdict and what would change it, then each section as it is reached", async ({
  page,
}) => {
  const errors = collectErrors(page);
  const sections = new Set<string>();
  page.on('request', (request) => {
    const query = (request.postDataJSON() as { query?: string } | null)?.query ?? '';
    const name = /query\s+(EdgeResult\w+)/.exec(query)?.[1];
    if (name) sections.add(name);
  });
  await page.goto('/edges?edge=momentum_12_1');
  await expect(page.getByRole('heading', { level: 1, name: 'Momentum 12-1' })).toBeVisible();
  // The head: the verdict, what would change it, with its meters and checks.
  await expect(
    page.getByText('Promising needs 40 out-of-sample trades: 6 so far, 34 to go.'),
  ).toBeVisible();
  await expect(page.getByRole('meter', { name: 'Out-of-sample trades' })).toBeVisible();
  await expect(page.getByText('Projected: 15 Mar 2027')).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Sections of this edge' });
  for (const name of [
    'Evidence',
    'How sure',
    'Where it worked',
    'Trades',
    'Definition',
    'Details',
  ]) {
    await expect(nav.getByRole('link', { name })).toBeVisible();
  }
  await expect(nav.getByRole('link', { name: 'Live record' })).toBeVisible(); // says why when nothing is recorded
  // Evidence: the curve (read as it comes near) and the figures of both sides of the split.
  await expect(page.getByRole('heading', { level: 2, name: 'Evidence' })).toBeVisible();
  await expect(page.getByRole('img', { name: /^Evidence curve of the picks/ })).toBeVisible();
  const figures = page.getByRole('grid', { name: 'In-sample, out-of-sample and all figures' });
  await expect(figures.getByRole('columnheader', { name: 'Out-of-sample · n=6' })).toBeVisible();
  await expect(figures.getByRole('row', { name: /Win rate/ })).toContainText('57.0%');
  // How sure: deciles, robustness with the multiple-testing line, decay with the paper not given.
  await nav.getByRole('link', { name: 'How sure' }).click();
  await expect(page.getByRole('list', { name: 'Mean outcome by decile' })).toBeVisible();
  await expect(
    page.getByText('Sharpe 1.10 over 70 trades with 3 variants becomes 0.40.'),
  ).toBeVisible();
  await expect(page.getByRole('list', { name: 'Decay by stage' })).toContainText('Not given');
  // Where it worked: the years, then the drawdown, read only when its view opens.
  await nav.getByRole('link', { name: 'Where it worked' }).click();
  await expect(page.getByRole('grid', { name: 'Year by year' })).toBeVisible();
  expect(sections.has('EdgeResultDrawdown')).toBe(false);
  await page.getByRole('tab', { name: 'Drawdown' }).click();
  await expect(page.getByRole('grid', { name: 'Deepest drawdowns' })).toBeVisible();
  await expect(
    page.getByRole('img', { name: 'Evidence curve below its previous high' }),
  ).toBeVisible();
  // The other cuts: by regime and by holding period (the basis marked), the cost strip under them.
  await page.getByRole('tab', { name: 'Regime' }).click();
  await expect(page.getByRole('grid', { name: 'By regime' })).toContainText('Stress');
  await page.getByRole('tab', { name: 'Holding period' }).click();
  await expect(page.getByRole('grid', { name: 'By holding period' })).toContainText(
    'Verdict basis',
  );
  await expect(page.getByRole('region', { name: 'Lift at each round-trip cost' })).toContainText(
    'Break-even',
  );
  // Trades: the ledger of the verdict's basis, a period switch and the file.
  await nav.getByRole('link', { name: 'Trades' }).click();
  const ledger = page.getByRole('grid', { name: 'Trade ledger' });
  await expect(ledger).toContainText('AAA');
  await expect(ledger.getByRole('row')).toHaveCount(3); // the header and two trades
  await page.getByRole('button', { name: 'Setup' }).click();
  await page.getByRole('list', { name: 'Result' }).getByRole('button', { name: /^Lost/ }).click();
  await page.keyboard.press('Escape');
  await expect(ledger.getByRole('row')).toHaveCount(2); // narrowed on the server
  await expect(ledger).not.toContainText('AAA');
  await expect(page.getByText('1 of 2').first()).toBeVisible();
  // The lost trade is in sample, so out of sample matches nothing: the way back is on the page.
  await page.getByRole('button', { name: /^Setup\s*, 1 active/ }).click();
  await page
    .getByRole('radiogroup', { name: 'In sample' })
    .getByRole('radio', { name: 'No' })
    .click();
  await page.keyboard.press('Escape');
  await expect(page.getByText('No edge trades match all 2 filters')).toBeVisible();
  await page.getByRole('button', { name: /^Switch off In sample gives 1/ }).click();
  await expect(ledger).toContainText('BBB');
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect(page.getByRole('button', { name: 'CSV' })).toBeVisible();
  // Details: the variant grid with its basis marked.
  await nav.getByRole('link', { name: 'Details' }).click();
  await page.getByRole('button', { name: /^Details/ }).click();
  await page.getByRole('heading', { level: 3, name: 'Variants tried' }).scrollIntoViewIfNeeded();
  await expect(
    page.getByRole('grid', { name: 'Variant grid: lift in points by holding period' }),
  ).toContainText('Verdict basis');
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('the list narrows by filter and search, and an edge offers Clone and Follow in dialogs', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/edges');
  const list = page.getByRole('grid', { name: 'Edges' });
  await expect(list.getByRole('row', { name: /Momentum 12-1/ })).toContainText('site edge');
  await page.getByRole('button', { name: 'Setup' }).click();
  await page.getByRole('radiogroup', { name: 'Mine' }).getByRole('radio', { name: 'Yes' }).click();
  await expect(page).toHaveURL(/f=mine/);
  await page.keyboard.press('Escape');
  await expect(list.getByRole('row', { name: /Momentum 12-1/ })).toHaveCount(0);
  await expect(page.getByText('No edges match this filter')).toBeVisible();
  await list.getByRole('button', { name: 'Clear all' }).click();
  await expect(page).not.toHaveURL(/f=/);
  await page.getByRole('searchbox', { name: 'Search edges' }).fill('winners');
  await expect(page).toHaveURL(/q=winners/);
  await expect(list.getByRole('row', { name: /S&P 500 index changes/ })).toHaveCount(0);
  await list.getByRole('row', { name: /Momentum 12-1/ }).click();
  await page.getByRole('button', { name: 'Follow', exact: true }).click();
  await expect(page.getByRole('dialog', { name: /Follow · Momentum 12-1/ })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('button', { name: 'Clone', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Name of your copy' })).toHaveValue(
    'my-momentum_12_1',
  );
  expect(errors).toEqual([]);
});

test('a user runs an evaluation of the chosen edge and sees it finish', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/edges?edge=momentum_12_1');
  await page.getByRole('button', { name: 'Run backtest' }).click();
  await expect(page.getByText('Done (exploratory)')).toBeVisible();
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('Screeners shows the track record of a screener in an edge and opens it in place', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await page.goto('/screeners');
  const headline = page
    .getByRole('table', { name: 'Screeners' })
    .getByRole('button', { name: 'Momentum 12-1' })
    .first();
  await expect(headline).toBeVisible();
  await headline.click();
  await expect(headline).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('list', { name: /^Edges of / })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Open edge / }).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('a user clones an edge, edits a screen in the Screen Builder, returns, saves and runs the backtest', async ({
  page,
}) => {
  const errors = collectErrors(page);
  const mock = await mockEdgesApi(page); // the builder's writes, recorded
  await page.goto('/edges?edge=momentum_12_1');
  await page.getByRole('button', { name: 'Clone', exact: true }).click();
  await page
    .getByRole('dialog', { name: 'Clone edge' })
    .getByRole('button', { name: 'Clone', exact: true })
    .click();
  await expect(page).toHaveURL(/\/test\/setup\/my-momentum_12_1$/);
  await expect(page.getByText('Your copy of an edge')).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Edge builder steps' });
  for (const step of [
    '1 · Idea',
    '2 · Screens',
    '3 · Picks',
    '4 · Trade',
    '5 · Compare against',
    '6 · Test and run',
  ]) {
    await expect(nav.getByRole('link', { name: step })).toBeVisible();
  }
  // Edit the draft, then a screen in the Screen Builder: the draft is kept while away.
  await page.getByRole('textbox', { name: /^Thesis/ }).fill('My own thesis');
  await page.getByRole('button', { name: 'Edit vrp_scanner in Screen Builder' }).click();
  await expect(page).toHaveURL(/\/test\/expert\/vrp_scanner\?returnTo=my-momentum_12_1$/);
  await page.getByRole('button', { name: 'Save and return to edge' }).click();
  await expect(page).toHaveURL(/\/test\/setup\/my-momentum_12_1$/);
  await expect(page.getByRole('textbox', { name: /^Thesis/ })).toHaveValue('My own thesis');
  await expectAccessible(page);
  await page.getByRole('button', { name: 'Save and run backtest' }).click();
  await expect(page.getByText('Backtest running')).toBeVisible();
  await expect(page.getByText('Backtest finished')).toBeVisible();
  expect(mock.saves).toHaveLength(1);
  expect(mock.saves[0]).toMatchObject({
    id: 'my-momentum_12_1',
    document: {
      extends: 'momentum_12_1',
      thesis: 'My own thesis',
      top_k: 50,
      screeners: ['momentum_12_1'],
      outcome: { cost_bps: 10, benchmark: 'SPY' },
    },
  });
  await page.getByRole('button', { name: 'Show result' }).click();
  await expect(page).toHaveURL(/\/edges\?edge=my-momentum_12_1$/);
  expect(errors).toEqual([]);
});

test('New edge opens the empty builder and Cancel goes back to the list', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/edges');
  await page.getByRole('button', { name: 'New edge' }).click();
  await expect(page).toHaveURL(/\/test\/setup$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Untitled edge' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save and run backtest' })).toBeDisabled();
  await page.getByRole('button', { name: '+ New screen' }).click();
  await expect(page).toHaveURL(/\/test\/expert\?returnTo=\.new$/);
  await page.goBack();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL(/\/edges$/);
  expect(errors).toEqual([]);
});

test('an old ?view= link opens the list narrowed by the filter it stood for', async ({ page }) => {
  await page.goto('/edges?view=rejected');
  const list = page.getByRole('grid', { name: 'Edges' });
  await expect(list.getByRole('row', { name: /S&P 500 index changes/ })).toBeVisible();
  await expect(list.getByRole('row', { name: /Momentum 12-1/ })).toHaveCount(0);
  await expect(
    page
      .getByRole('group', { name: 'Applied filters' })
      .getByRole('button', { name: /^Status Rejected/ }),
  ).toBeVisible();
  await expectAccessible(page);
});
