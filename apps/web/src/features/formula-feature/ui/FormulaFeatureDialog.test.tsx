import { render, screen, waitFor } from '@testing-library/react';
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
    await userEvent.click(screen.getByRole('textbox', { name: 'Formula' }));
    await userEvent.paste('a - b');
    expect(POST).not.toHaveBeenCalled();
    expect(await screen.findByText('num (float32)')).toBeInTheDocument();
    expect(POST).toHaveBeenCalledTimes(1);
    expect(POST).toHaveBeenCalledWith('/features/check', { body: { expr: 'a - b', sample: 5 } });
    expect(screen.getByText('rollup.iv30@v1.iv30, rollup.price_stats@v2.hv30')).toBeInTheDocument();
    expect(screen.getByText('90 of 100 have a value')).toBeInTheDocument();
    expect(screen.getByText('0.12')).toBeInTheDocument();
  });

  it('says why a formula does not check and cannot be saved', async () => {
    setup();
    await userEvent.click(screen.getByRole('textbox', { name: 'Formula' }));
    await userEvent.paste('nope');
    expect(await screen.findByText('This formula does not check')).toBeInTheDocument();
    expect(screen.getByText(/unknown feature 'nope'/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save feature' })).toBeDisabled();
  });

  it('saves a named feature with its type, unit and meaning, then reports its field', async () => {
    const { onSaved, onOpenChange, baseElement } = setup();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'vol_gap');
    await userEvent.click(screen.getByRole('textbox', { name: 'Formula' }));
    await userEvent.paste('a - b');
    await screen.findByText('num (float32)');
    await userEvent.type(screen.getByRole('textbox', { name: 'What it is' }), 'IV minus HV');
    await userEvent.type(
      screen.getByRole('textbox', { name: 'When it is empty' }),
      'a vol is missing',
    );
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

  it('asks for a valid name', async () => {
    setup();
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Vol Gap');
    expect(screen.getByText(/Use lowercase letters, digits and _/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save feature' })).toBeDisabled();
  });
});
