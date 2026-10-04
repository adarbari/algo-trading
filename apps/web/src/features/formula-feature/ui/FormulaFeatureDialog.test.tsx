import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FormulaFeatureDialog } from './FormulaFeatureDialog';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});

const POST = vi.mocked(api.POST);
const ok = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) });

const CHECK = {
  expr: 'a - b',
  type: 'num',
  dtype: 'float32',
  categories: null,
  inputs: ['rollup.iv30@v1.iv30', 'rollup.price_stats@v2.hv30'],
  licence: 'open',
  session: '2026-10-02',
  rows: 100,
  non_null: 90,
  sample: [{ instrument_id: 'EQ:1', value: 0.12 }],
};

beforeEach(() => {
  POST.mockReset();
  POST.mockImplementation(((path: string, init: { body: { expr?: string } }) => {
    if (path === '/features/check') {
      return Promise.resolve(
        init.body.expr?.includes('nope')
          ? {
              error: { detail: "1:1: unknown feature 'nope'" },
              response: new Response(null, { status: 400 }),
            }
          : ok({ ...CHECK, expr: init.body.expr }),
      );
    }
    return Promise.resolve(
      ok({
        name: 'vol_gap',
        field: 'feature.vol_gap',
        theme: 'builder',
        dtype: 'float32',
        kind: 'expression',
        inputs: [],
      }),
    );
  }) as never);
});

/** Sets a field without moving focus (the dialog moves focus into itself as it opens). */
function fill(name: string, value: string) {
  fireEvent.change(screen.getByRole('textbox', { name }), { target: { value } });
}

function setup() {
  const onSaved = vi.fn();
  const onOpenChange = vi.fn();
  const view = render(
    <TestQueryProvider>
      <FormulaFeatureDialog open onOpenChange={onOpenChange} onSaved={onSaved} />
    </TestQueryProvider>,
  );
  return { onSaved, onOpenChange, ...view };
}

describe('FormulaFeatureDialog', () => {
  it('checks the formula as it is typed (debounced) and shows what it reads and samples', async () => {
    setup();
    fill('Formula', 'a - b');
    expect(POST).not.toHaveBeenCalled();
    expect(await screen.findByText('num (float32)', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/features/check', { body: { expr: 'a - b', sample: 5 } });
    expect(screen.getByText('rollup.iv30@v1.iv30, rollup.price_stats@v2.hv30')).toBeInTheDocument();
    expect(screen.getByText('90 of 100 have a value')).toBeInTheDocument();
    expect(screen.getByText('0.12')).toBeInTheDocument();
  });

  it('says why a formula does not check and cannot be saved', async () => {
    setup();
    fill('Formula', 'nope');
    expect(
      await screen.findByText('This formula does not check', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/unknown feature 'nope'/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save feature' })).toBeDisabled();
  });

  it('saves a named feature with its type, unit and meaning, then reports its field', async () => {
    const { onSaved, onOpenChange, baseElement } = setup();
    fill('Name', 'vol_gap');
    fill('Formula', 'a - b');
    await screen.findByText('num (float32)', {}, { timeout: 4000 });
    fill('What it is', 'IV minus HV');
    fill('When it is empty', 'a vol is missing');
    await expectNoA11yViolations(baseElement);
    await userEvent.click(screen.getByRole('button', { name: 'Save feature' }));
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith('feature.vol_gap');
    });
    expect(POST).toHaveBeenCalledWith('/features/user', {
      body: {
        name: 'vol_gap',
        expr: 'a - b',
        dtype: 'float32',
        unit: 'ratio',
        description: 'IV minus HV',
        null_meaning: 'a vol is missing',
        theme: 'builder',
      },
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('asks for a valid name', () => {
    setup();
    fill('Name', 'Vol Gap');
    expect(screen.getByText(/Use lowercase letters, digits and _/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save feature' })).toBeDisabled();
  });
});
