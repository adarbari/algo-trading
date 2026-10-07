import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideFieldsIndex } from './GuideFieldsIndex';

const hooks = vi.hoisted(() => ({ useFeatureCatalogue: vi.fn(), useGuideIndex: vi.fn() }));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));
vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
}));

const use = (intent: string) => ({
  intent,
  op: 'gte',
  value: 1,
  mode: 'soft',
  tolerance: 0,
  onMiss: null,
  note: 'n',
});
const field = (name: string, theme: string, reads: string, intents: string[] = []) => ({
  name,
  kind: 'rollup',
  description: reads,
  guide: { theme, reads, uses: intents.map(use), caveats: [], sources: [] },
});

const catalogue = [
  field('feature.zeta', 'volume', 'Zeta reads. More.', ['Heavy volume']),
  field('feature.alpha', 'volume', 'Alpha reads.'),
  field('feature.rsi_14', 'momentum and trend', 'Relative strength.', ['Heavy volume', 'Oversold']),
  { name: 'instrument.sector', kind: 'instrument', description: 'GICS sector', guide: null },
];

const index = {
  sections: [{ id: 'fields', title: 'Fields', purpose: 'Every catalogue field.', entries: 3 }],
  themeGroups: [
    { id: 'chart', title: 'The chart', themes: [{ theme: 'momentum and trend', fields: 1 }] },
    { id: 'tradeable', title: 'Who is tradeable', themes: [{ theme: 'volume', fields: 2 }] },
  ],
  intents: [
    { intent: 'Heavy volume', fields: 2 },
    { intent: 'Oversold', fields: 1 },
  ],
};

beforeEach(() => {
  hooks.useFeatureCatalogue.mockReturnValue(fakeQuery(catalogue));
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
});

const setup = (props: Parameters<typeof GuideFieldsIndex>[0] = { onViewChange: vi.fn() }) =>
  render(<GuideFieldsIndex {...props} />);

describe('GuideFieldsIndex', () => {
  it('groups the themes as the server orders them, each with its count', () => {
    setup({ onViewChange: vi.fn() });
    expect(screen.getByText('Every catalogue field.')).toBeInTheDocument();
    const groups = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'));
    expect(groups).toEqual(['The chart', 'Who is tradeable']);
    expect(screen.getByRole('link', { name: 'Volume · 2' })).toHaveAttribute(
      'href',
      '/guide/fields?theme=volume',
    );
  });

  it('lists a theme’s guided fields with the first sentence of how to read each', () => {
    setup({ theme: 'volume', onViewChange: vi.fn() });
    expect(screen.getByRole('heading', { level: 2, name: 'Volume' })).toBeInTheDocument();
    expect(screen.getAllByRole('link').map((l) => l.textContent)).toEqual([
      'All themes',
      'feature.zeta',
      'feature.alpha',
    ]);
    expect(screen.getByText('Zeta reads.')).toBeInTheDocument();
  });

  it('lists the intents with their counts, and the fields offering one', () => {
    const { unmount } = setup({ view: 'intent', onViewChange: vi.fn() });
    expect(screen.getByRole('link', { name: 'Heavy volume · 2' })).toHaveAttribute(
      'href',
      '/guide/fields?view=intent&intent=Heavy+volume',
    );
    unmount();
    setup({ view: 'intent', intent: 'Oversold', onViewChange: vi.fn() });
    expect(
      within(
        screen.getByRole('heading', { level: 2, name: 'Oversold' }).parentElement as HTMLElement,
      )
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual(['All intents', 'feature.rsi_14']);
  });

  it('lists every guided field A to Z, and leaves out a field without a guide entry', () => {
    setup({ view: 'az', onViewChange: vi.fn() });
    expect(screen.getAllByRole('link').map((l) => l.textContent)).toEqual([
      'feature.alpha',
      'feature.rsi_14',
      'feature.zeta',
    ]);
  });

  it('asks for another view', async () => {
    const onViewChange = vi.fn();
    setup({ onViewChange });
    await userEvent.click(screen.getByRole('radio', { name: 'A to Z' }));
    expect(onViewChange).toHaveBeenCalledWith('az');
  });

  it('shows loading and a retry on error', async () => {
    hooks.useGuideIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = setup();
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    rerender(<GuideFieldsIndex onViewChange={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = setup({ view: 'az', onViewChange: vi.fn() });
    await expectNoA11yViolations(container);
  });
});
