/**
 * Trader > Screeners end to end, against the production build with the API mocked from
 * fixtures shaped like the authoring and preview endpoints (builder-api.ts): the list with its
 * presets, the Builder (criteria, live debounced preview with summary, funnel and rows, draft
 * save / discard / finalize, rebase, a preview error naming its
 * criterion), adding a formula feature, copying a preset, starting a new screener, accessibility.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockBuilderApi } from './builder-api';
import { mockApi } from './mock-api';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    // The mocked 400s (preview error, bad formula) log a network error by design.
    if (msg.type() === 'error' && !msg.text().includes('status of 400')) errors.push(msg.text());
  });
  return errors;
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('the list shows your screeners and the site presets in one list', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/screeners');
  await expect(page.getByRole('heading', { level: 1, name: 'Screeners' })).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Trader sections' })
      .getByRole('link', { name: 'Screeners' }),
  ).toHaveAttribute('aria-current', 'page');
  const list = page.getByRole('table', { name: 'Screeners' });
  const rowOf = (name: RegExp) =>
    list.getByRole('row').filter({ has: page.getByRole('button', { name }) });
  await expect(rowOf(/^my-vrp Mine/)).toContainText('No run today');
  // A draft that was never finalized is listed too.
  await expect(list.getByRole('button', { name: /^idea-draft Mine/ })).toContainText('Draft');
  const preset = list.getByRole('button', { name: /^vrp_scanner Preset/ });
  await expect(rowOf(/^vrp_scanner Preset/)).toContainText('12');
  await expect(rowOf(/^vrp_scanner Preset/)).toContainText('+3');
  await expect(preset).toHaveAttribute('aria-expanded', 'false');
  await expect(list.getByRole('button', { name: /^short_premium_liquidity Preset/ })).toBeVisible();
  // The segments and the search narrow the list.
  await page.getByRole('radio', { name: 'Presets' }).click();
  await expect(list.getByRole('button', { name: /Mine/ })).toHaveCount(0);
  await page.getByRole('radio', { name: 'All' }).click();
  await page.getByRole('searchbox', { name: 'Search screeners' }).fill('idea');
  await expect(list.getByRole('button')).toHaveCount(1);
  await expectAccessible(page);
  expect(errors).toEqual([]);
});

test('a row opens in place, one at a time, with its criteria, hits and actions', async ({
  page,
}) => {
  await page.goto('/screeners');
  const list = page.getByRole('table', { name: 'Screeners' });
  const preset = list.getByRole('button', { name: /^vrp_scanner Preset/ });
  await preset.click();
  await expect(preset).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('heading', { level: 3, name: 'Criteria' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: 'Top hits' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Duplicate to edit' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Playbook' })).toHaveAttribute(
    'href',
    '/guide/playbooks/vrp_scanner',
  );
  await list.getByRole('button', { name: /^my-vrp Mine/ }).click();
  await expect(preset).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('button', { name: 'Edit criteria' })).toBeVisible();
  await expectAccessible(page);
  await preset.click();
  await page.getByRole('button', { name: 'View 12 hits' }).click();
  await expect(page).toHaveURL(/\/screeners\/vrp_scanner$/);
});

test('the list’s Playbook link and the Builder header’s link open the preset’s playbook', async ({
  page,
}) => {
  await page.goto('/screeners');
  await page.getByRole('button', { name: /^vrp_scanner Preset/ }).click();
  await page.getByRole('link', { name: 'Playbook' }).click();
  await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
  await page.goto('/screeners/vrp_scanner/edit');
  await page.getByRole('link', { name: 'Playbook' }).click();
  await expect(page).toHaveURL(/\/guide\/playbooks\/vrp_scanner$/);
});

for (const width of [800, 1024, 1280]) {
  test(`an open row's actions are in view and can be clicked at ${String(width)} px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto('/screeners');
    await page.getByRole('button', { name: /^vrp_scanner Preset/ }).click();
    const button = page.getByRole('button', { name: 'Duplicate to edit' });
    await expect(button).toBeInViewport({ ratio: 1 });
    await button.click();
    await expect(page.getByRole('dialog', { name: 'Copy to my screeners' })).toBeVisible();
  });
}

for (const theme of ['dark', 'light'] as const) {
  test(`the Builder shows the criteria and the live preview (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.goto('/screeners/my-vrp/edit');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeVisible();
    await expect(page.getByText('DRAFT v2', { exact: true })).toBeVisible();
    await expect(page.getByText('Your copy of vrp_scanner v1')).toBeVisible();
    await expect(page.getByText('Rebase on v2')).toBeVisible();
    await expect(page.getByRole('radiogroup', { name: /Mode of/ })).toHaveCount(4);
    await expect(page.getByRole('radio', { name: 'Soft' }).first()).toBeVisible();
    await expect(page.getByText(/Find instruments where/)).toBeVisible();
    // The preview: summary, funnel, rows.
    await expect(
      page.getByRole('list', { name: 'Run summary' }).or(page.getByLabel('Run summary')).first(),
    ).toBeVisible();
    await expect(page.getByText('Missing data', { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole('list', { name: 'Funnel (gating criteria)' }).getByRole('listitem'),
    ).toHaveCount(4);
    const results = page.getByRole('grid', { name: 'Preview results' });
    await expect(results.getByRole('row', { name: /AAPL/ })).toContainText('Qualified');
    await expect(results.getByRole('row', { name: /KO/ })).toContainText('spread within tolerance');
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('editing a threshold previews after 300 ms, then saves the draft and finalizes', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await expect(page.getByRole('grid', { name: 'Preview results' })).toBeVisible();
  const before = mock.previews.length;
  const threshold = page.getByRole('spinbutton', { name: 'Threshold' }).first();
  await threshold.fill('60');
  await threshold.press('Enter');
  await expect(page.getByText('DRAFT v2 · unsaved changes')).toBeVisible();
  await expect.poll(() => mock.previews.length).toBe(before + 1);
  const spec = mock.previews.at(-1) as { criteria: { iv30: { value: number } } };
  expect(spec.criteria.iv30.value).toBe(0.6);

  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  await expect(page.getByText('DRAFT v2', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Finalize v2' }).click();
  await expect.poll(() => mock.finalised).toEqual(['my-vrp']);
  await expect(page.getByText('Finalised v2')).toBeVisible();
  await expect(page.getByText('v2 · finalized')).toBeVisible();
});

test('changing a mode saves a tolerance with it', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('radio', { name: 'Soft' }).first().check();
  await expect(page.getByRole('spinbutton', { name: 'Tolerance' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  const criteria = mock.drafts[0]?.document['criteria'] as Record<
    string,
    { mode: string; tolerance: unknown }
  >;
  expect(criteria['iv30']).toMatchObject({ mode: 'soft', tolerance: 0 });
});

test("a criterion's help button opens the field's drawer and Use this fills that row", async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  const row = page.getByRole('combobox', { name: 'Feature or formula' }).first();
  await expect(row).toHaveValue('IV30');
  await page
    .getByRole('button', { name: /^What is IV30/ })
    .first()
    .click();
  const drawer = page.getByRole('dialog');
  await expect(drawer).toContainText('Rich premium to sell');
  await expectAccessible(page);
  await drawer.getByRole('button', { name: 'Use this: Cheap options to buy' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Operator' }).first()).toHaveText(/≤/);
  await expect(page.getByRole('spinbutton', { name: 'Threshold' }).first()).toHaveValue('20.0');
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  const criteria = mock.drafts[0]?.document['criteria'] as Record<
    string,
    { op: string; value: number }
  >;
  expect(criteria['iv30']).toMatchObject({ op: 'lte', value: 0.2 });
});

test('discarding the draft goes back to the saved version', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('button', { name: 'Discard' }).click();
  await expect.poll(() => mock.discarded).toEqual(['my-vrp']);
  await expect(page.getByText('v1 · finalized')).toBeVisible();
});

test('there is no schedule switch: a finalised screen runs nightly (ADR 0033)', async ({
  page,
}) => {
  await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await expect(page.getByRole('heading', { level: 1, name: 'my-vrp' })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Run nightly' })).toHaveCount(0);
});

test('rebasing re-pins the preset and drops the banner', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('button', { name: 'Rebase on v2' }).click();
  await expect.poll(() => mock.rebased).toEqual(['my-vrp']);
  await expect(page.getByText('Rebase on v2')).toHaveCount(0);
});

test('a preview error names the criterion it came from', async ({ page }) => {
  await mockBuilderApi(page, { failPreviewOn: 'spread' });
  await page.goto('/screeners/my-vrp/edit');
  await expect(
    page.getByText(/my-vrp\.criteria\.spread\.field: unknown field/).first(),
  ).toBeVisible();
  await expectAccessible(page);
});

test('adds a formula feature as a criterion', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('button', { name: '+ Add formula feature' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add formula feature' });
  await dialog.getByLabel('Name').fill('vol_gap');
  await dialog.getByLabel('Formula').fill('rollup.iv30@v1.iv30 - rollup.price_stats@v2.hv30');
  await expect(dialog.getByText('num (float32)')).toBeVisible();
  await expect(dialog.getByText('3,600 of 11,427 have a value')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Save feature' })).toBeDisabled();
  await dialog.getByLabel('What it is').fill('IV minus HV');
  await dialog.getByLabel('When it is empty').fill('either vol is missing');
  await dialog.getByRole('button', { name: 'Save feature' }).click();
  await expect.poll(() => mock.features.length).toBe(1);
  expect(mock.features[0]).toMatchObject({ name: 'vol_gap', dtype: 'float32', unit: 'ratio' });
  await expect(page.getByRole('radiogroup', { name: /Mode of/ })).toHaveCount(5);
});

test('a formula that does not check says why', async ({ page }) => {
  await page.goto('/screeners/my-vrp/edit');
  await page.getByRole('button', { name: '+ Add formula feature' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add formula feature' });
  await dialog.getByLabel('Formula').fill('nope + 1');
  await expect(dialog.getByText('This formula does not check')).toBeVisible();
  await expect(dialog.getByText(/unknown feature 'nope'/)).toBeVisible();
  await expectAccessible(page);
});

test('a preset is copied to a named screener from the list', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners');
  await page.getByRole('button', { name: /^vrp_scanner Preset/ }).click();
  await page.getByRole('button', { name: 'Duplicate to edit' }).click();
  const dialog = page.getByRole('dialog', { name: 'Copy to my screeners' });
  await expect(dialog.getByLabel('Name of your copy')).toHaveValue('my-vrp_scanner');
  await dialog.getByLabel('Name of your copy').fill('my-copy');
  await dialog.getByRole('button', { name: 'Copy' }).click();
  await expect.poll(() => mock.copies).toEqual([{ id: 'my-copy', preset: 'vrp_scanner' }]);
  await expect(page).toHaveURL(/\/screeners\/my-copy\/edit/);
  await expect(page.getByText('Your copy of vrp_scanner v2')).toBeVisible();
});

for (const theme of ['dark', 'light'] as const) {
  test(`a preset opens with its live preview, no copy yet (${theme})`, async ({ page }) => {
    const errors = collectErrors(page);
    const mock = await mockBuilderApi(page);
    await page.goto('/screeners/vrp_scanner/edit');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expect(page.getByRole('heading', { level: 1, name: 'vrp_scanner' })).toBeVisible();
    await expect(page.getByText('Site preset', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('grid', { name: 'Preview results' })).toBeVisible();
    await expect(page.getByRole('radiogroup', { name: /Mode of/ })).toHaveCount(4);
    // Nothing is locked, and nothing was copied by looking.
    await expect(page.getByRole('button', { name: '+ Add criterion' })).toBeEnabled();
    expect(mock.copies).toEqual([]);
    expect(mock.previews[0]).toMatchObject({ id: 'vrp_scanner', extends: 'vrp_scanner@2' });
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('the first edit of a preset makes your copy, which you change, rerun and finalize', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner/edit');
  await expect(page.getByRole('grid', { name: 'Preview results' })).toBeVisible();
  const before = mock.previews.length;
  const threshold = page.getByRole('spinbutton', { name: 'Threshold' }).first();
  await threshold.fill('60');
  await threshold.press('Enter');
  await expect.poll(() => mock.copies).toEqual([{ id: 'vrp_scanner', preset: 'vrp_scanner' }]);
  await expect(page.getByText('Your copy of vrp_scanner v2')).toBeVisible();
  await expect(page.getByText('DRAFT v1 · unsaved changes')).toBeVisible();
  // The edit reruns the preview on the copy's document.
  await expect.poll(() => mock.previews.length).toBeGreaterThan(before);
  expect(mock.previews.at(-1)).toMatchObject({
    extends: 'vrp_scanner@2',
    criteria: { iv30: { value: 0.6 } },
  });
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  expect(mock.drafts[0]?.document).toMatchObject({ extends: 'vrp_scanner@2' });
  await page.getByRole('button', { name: 'Finalize v1' }).click();
  await expect.poll(() => mock.finalised).toEqual(['vrp_scanner']);
  expect(mock.copies).toHaveLength(1);
});

test('an inherited tie-break can be cleared in your copy', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners/vrp_scanner/edit');
  await expect(page.getByRole('combobox', { name: 'Feature or formula' }).last()).toHaveValue(
    'IV − HV',
  );
  await page.getByRole('button', { name: 'Clear tie-break' }).click();
  await expect(page.getByRole('button', { name: 'Clear tie-break' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  expect(mock.drafts[0]?.document).toMatchObject({
    extends: 'vrp_scanner@2',
    rank: { tie_break: '' },
  });
});

test('a new screener starts with the base gates as criteria', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await page.goto('/screeners');
  await page.getByRole('button', { name: '+ New screener' }).click();
  await expect(page).toHaveURL(/\/screeners\/new/);
  await expect(page.getByRole('heading', { level: 1, name: 'New screener' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Name' }).fill('Bad Name');
  await expect(page.getByText('Use 1-64 of a-z, 0-9, _ and -.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Name' }).fill('fresh');
  await page.getByRole('button', { name: 'Create draft' }).click();
  await expect.poll(() => mock.drafts.map((d) => d.id)).toEqual(['fresh']);
  expect(mock.drafts[0]?.document).toMatchObject({
    kind: 'screener',
    impl: 'rules',
    criteria: {
      security_type: { field: 'instrument.security_type', op: 'in' },
      status: { field: 'instrument.status', op: 'eq', value: 'ACTIVE' },
      optionable: { field: 'instrument.optionable', op: 'eq', value: true },
    },
  });
  expect(mock.drafts[0]?.document).not.toHaveProperty('selection'); // ADR 0030
  await expect(page).toHaveURL(/\/screeners\/fresh\/edit/);
  // The base gates are ordinary criteria: three hard rows to edit or remove, then add more.
  await expect(page.getByRole('radiogroup', { name: /Mode of/ })).toHaveCount(3);
  await expectAccessible(page);
  await page.getByRole('button', { name: '+ Add criterion' }).click();
  await expect(page.getByRole('radiogroup', { name: /Mode of/ })).toHaveCount(4);
});
