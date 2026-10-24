import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { stubElementSize } from '@/shared/lib/testing';

import { useFilterState } from '../api/use-filter-state';
import { SurfaceFilterBar } from './SurfaceFilterBar';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const DOLLAR = 'rollup.volume@v1.dollar_volume';
const RET = 'rollup.price_stats@v2.ret_20d';

const entry = (name: string, description: string) => ({
  name,
  kind: 'rollup',
  source: 'x',
  dtype: 'float',
  format: 'NUMBER',
  description,
  nullMeaning: '',
  version: 1,
  group: 'g',
  key: null,
  inputs: [],
  unit: null,
  range: null,
  categories: [],
  scope: 'site',
  owner: null,
  licence: 'open',
  guide: { theme: 't', reads: 'r', summary: description },
});

const definition = (id: string, label: string, kind: string, unit: string | null = null) => ({
  id,
  label,
  group: 'MORE',
  kind,
  guide: `field:${id.replace('feature:', '')}`,
  options: [],
  bins: [],
  windowUnit: null,
  unit,
});

let asked: { surface: string; withFeatures?: string[] | null }[] = [];

beforeEach(() => {
  asked = [];
  vi.mocked(gql).mockImplementation((document, variables) => {
    const text = String(document);
    if (text.includes('query FilterFeatures')) {
      return Promise.resolve({
        filterFeatures: [
          {
            name: DOLLAR,
            label: 'dollar volume',
            kind: 'RANGE',
            guide: `field:${DOLLAR}`,
            synonyms: ['liquid'],
          },
          { name: RET, label: 'ret 20d', kind: 'RANGE', guide: `field:${RET}`, synonyms: [] },
        ],
      });
    }
    if (text.includes('query FeatureCatalogue')) {
      return Promise.resolve({
        catalogue: [entry(DOLLAR, 'Dollars traded per day'), entry(RET, 'Return over 20 sessions')],
      });
    }
    const v = variables as { surface: string; withFeatures?: string[] | null };
    asked.push(v);
    const made = (v.withFeatures ?? []).map((f) =>
      definition(
        `feature:${f}`,
        f === RET ? 'ret 20d' : 'dollar volume',
        'RANGE',
        f === RET ? 'PERCENT' : null,
      ),
    );
    return Promise.resolve({
      filterSet: { surface: 'ideas', label: 'Ideas', searchable: true, filters: made },
    });
  });
});

function Bar({ f = '' }: { f?: string }) {
  const [value, setValue] = useState<string | undefined>(f || undefined);
  const state = useFilterState(value, setValue);
  return (
    <TestQueryProvider>
      <SurfaceFilterBar surface="ideas" state={state} facets={null} />
      <output aria-label="f">{value ?? ''}</output>
    </TestQueryProvider>
  );
}

stubElementSize();

describe('More filters', () => {
  it('finds a feature by a phrasebook word and starts a filter with the control of its kind', async () => {
    const user = userEvent.setup();
    render(<Bar />);
    await user.click(await screen.findByRole('button', { name: 'More filters' }));
    await user.type(await screen.findByRole('combobox', { name: 'Find a filter' }), 'liquid');
    await user.click(await screen.findByRole('option', { name: new RegExp(DOLLAR) }));
    const dialog = screen.getByRole('dialog', { name: 'More filters' });
    expect(await within(dialog).findByRole('group', { name: 'dollar volume' })).toBeInTheDocument();
    expect(asked.at(-1)?.withFeatures).toEqual([DOLLAR]);
    await user.type(within(dialog).getByRole('spinbutton', { name: 'Min' }), '5{Enter}');
    expect(screen.getByLabelText('f')).toHaveTextContent(`feature%3A${DOLLAR}:5..`);
  });

  it('asks for the definitions of the features already in the URL', async () => {
    render(<Bar f={`feature%3A${RET}:..0.1`} />);
    expect(await screen.findByRole('button', { name: /^ret 20d/ })).toBeInTheDocument();
    expect(asked.at(-1)?.withFeatures).toEqual([RET]);
  });

  it('shows a fraction as a percent, in the chip and the control, and sends it as stored', async () => {
    const user = userEvent.setup();
    render(<Bar f={`feature%3A${RET}:0.05..0.2`} />);
    expect(await screen.findByRole('button', { name: /^ret 20d 5%–20%/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'More filters' }));
    const dialog = await screen.findByRole('dialog', { name: 'More filters' });
    const min = within(dialog).getByRole('spinbutton', { name: 'Min' });
    expect(min).toHaveDisplayValue('5');
    await user.clear(min);
    await user.type(min, '10{Enter}');
    expect(screen.getByLabelText('f')).toHaveTextContent('0.1..0.2');
  });
});
