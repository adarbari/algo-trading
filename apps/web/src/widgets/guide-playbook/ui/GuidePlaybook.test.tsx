import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { GuidePlaybook } from './GuidePlaybook';

const hooks = vi.hoisted(() => ({ useGuidePlaybook: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuidePlaybook: hooks.useGuidePlaybook,
}));

stubElementSize();

const plain = (text: string) => ({ segments: [{ text }] });
const volume = 'feature.rel_volume';

const playbook = {
  id: 'breakout',
  name: 'Breakout',
  family: 'breakouts',
  familyTitle: 'Breakouts',
  version: 1,
  prose: {
    summary: plain('Finds shares that closed above their one-month high.'),
    hit: plain('A close above the prior 20-session high.'),
    notChecked: {
      segments: [{ text: 'Whether the break holds, or the market regime.' }],
    },
    beforeActing: [
      {
        segments: [
          { text: 'Earnings days run 3 to 10 times normal volume; read ' },
          { text: volume, field: volume },
          { text: ' with care.' },
        ],
      },
    ],
    sources: ['O’Neil, How to Make Money in Stocks'],
  },
  criteria: [
    {
      name: 'breakout_20d',
      asks: 'Closed above the 20-session high',
      field: 'feature.breakout_magnitude_20d',
      rule: 'gt 0',
      mode: 'hard',
      onMiss: null,
    },
    {
      name: 'not_extended',
      asks: null,
      field: 'feature.stretch_sma20_atr',
      rule: 'lte 3 soft tolerance 1.0',
      mode: 'soft',
      onMiss: 'WATCH',
    },
  ],
  tieBreak: 'feature.breakout_magnitude_20d',
  tieBreakDescending: true,
  related: [
    { id: 'failed_breakout', name: 'Failed breakout', reason: 'the same break after it fails' },
  ],
  situations: [{ slug: 'earnings-gap', name: 'Earnings gap inside the window', fields: [volume] }],
};

function setup() {
  const onSeeHits = vi.fn();
  const onOpenBuilder = vi.fn();
  const view = render(
    <GuidePlaybook id="breakout" onSeeHits={onSeeHits} onOpenBuilder={onOpenBuilder} />,
  );
  return { onSeeHits, onOpenBuilder, ...view };
}

beforeEach(() => {
  hooks.useGuidePlaybook.mockReturnValue(fakeQuery(playbook));
});

describe('GuidePlaybook', () => {
  it('heads the page with the preset id and version, the name and the summary as the hero', () => {
    setup();
    expect(screen.getByText('site preset · breakout v1 · Breakouts')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Breakout' })).toBeInTheDocument();
    expect(
      screen.getByText('Finds shares that closed above their one-month high.'),
    ).toBeInTheDocument();
  });

  it('opens today’s hits and the Builder from the two buttons', async () => {
    const { onSeeHits, onOpenBuilder } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'See today’s hits' }));
    expect(onSeeHits).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('button', { name: 'Open in Builder' }));
    expect(onOpenBuilder).toHaveBeenCalledOnce();
  });

  it('shows what a hit looks like beside what it does not check', () => {
    setup();
    expect(
      within(screen.getByRole('region', { name: 'What a hit looks like' })).getByText(
        'A close above the prior 20-session high.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('What it does not check')).toBeInTheDocument();
    expect(screen.getByText(/Whether the break holds/)).toBeInTheDocument();
  });

  it('lists the criteria: what it asks, the field linked, the rule and what a miss does', () => {
    setup();
    const table = within(screen.getByRole('grid', { name: 'Breakout criteria' }));
    const first = within(table.getByRole('row', { name: /Closed above the 20-session high/ }));
    expect(first.getByRole('link', { name: 'feature.breakout_magnitude_20d' })).toHaveAttribute(
      'href',
      '/guide/fields/feature.breakout_magnitude_20d',
    );
    expect(first.getByText('gt 0')).toBeInTheDocument();
    expect(first.getByText('reject')).toBeInTheDocument();
    const soft = within(table.getByRole('row', { name: /not_extended/ }));
    expect(soft.getByText('lte 3 soft tolerance 1.0')).toBeInTheDocument();
    expect(soft.getByText('WATCH')).toBeInTheDocument();
    expect(
      screen.getByText('Ranked by feature.breakout_magnitude_20d, highest first.'),
    ).toBeInTheDocument();
  });

  it('links the fields in the caveats and the situations that fool its fields', () => {
    setup();
    const before = screen.getByRole('region', { name: 'Before you act on a hit' });
    expect(within(before).getByRole('link', { name: volume })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(volume)}`,
    );
    expect(
      within(before).getByRole('link', { name: 'Earnings gap inside the window' }),
    ).toHaveAttribute('href', '/guide/situations/earnings-gap');
  });

  it('links related playbooks with their reasons, and lists the sources', () => {
    setup();
    const related = screen.getByRole('region', { name: 'Related playbooks' });
    expect(within(related).getByRole('link', { name: 'Failed breakout' })).toHaveAttribute(
      'href',
      '/guide/playbooks/failed_breakout',
    );
    expect(within(related).getByText(/the same break after it fails/)).toBeInTheDocument();
    expect(screen.getByText('O’Neil, How to Make Money in Stocks')).toBeInTheDocument();
  });

  it('shows the criteria alone when no prose is written for the preset', () => {
    hooks.useGuidePlaybook.mockReturnValue(
      fakeQuery({ ...playbook, prose: null, related: [], situations: [] }),
    );
    setup();
    expect(screen.getByText(/No playbook prose is written/)).toBeInTheDocument();
    expect(screen.getByRole('grid', { name: 'Breakout criteria' })).toBeInTheDocument();
    expect(screen.queryByText('What it does not check')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Before you act on a hit' })).toBeNull();
  });

  it('shows loading, an error with a retry, and an unknown playbook', async () => {
    hooks.useGuidePlaybook.mockReturnValue(fakeQuery(undefined));
    const { rerender } = setup();
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuidePlaybook.mockReturnValue(failed);
    rerender(<GuidePlaybook id="breakout" onSeeHits={vi.fn()} onOpenBuilder={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuidePlaybook.mockReturnValue(fakeQuery(null));
    rerender(<GuidePlaybook id="nope" onSeeHits={vi.fn()} onOpenBuilder={vi.fn()} />);
    expect(screen.getByText('No such playbook')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = setup();
    await expectNoA11yViolations(container);
  });
});
