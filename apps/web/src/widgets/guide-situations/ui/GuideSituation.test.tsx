import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideSituation } from './GuideSituation';
import { GuideSituationsIndex } from './GuideSituationsIndex';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn(), useGuideSituation: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
  useGuideSituation: hooks.useGuideSituation,
}));

const volume = 'feature.rel_volume';
const situation = {
  slug: 'earnings-gap',
  name: 'Earnings gap inside the window',
  signs: { segments: [{ text: 'A report in the next 30 days lifts the reading.' }] },
  do: {
    segments: [
      { text: 'Read ' },
      { text: volume, field: volume },
      { text: ' beside the earnings date.' },
    ],
  },
  affects: [volume, 'feature.atr_ratio_5_20'],
  playbooks: [{ id: 'breakout', name: 'Breakout', fields: [volume] }],
};

const index = {
  sections: [
    { id: 'situations', title: 'Situations', purpose: 'States that fool fields.', entries: 2 },
  ],
  situations: [
    { name: 'Pending takeover', fields: 12, slug: 'pending-takeover' },
    { name: 'Earnings gap inside the window', fields: 1, slug: 'earnings-gap' },
  ],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
  hooks.useGuideSituation.mockReturnValue(fakeQuery(situation));
});

describe('GuideSituation', () => {
  it('shows the signs, what to do with the fields linked, and the fields it fools', () => {
    render(<GuideSituation slug="earnings-gap" />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'Earnings gap inside the window' }),
    ).toBeInTheDocument();
    expect(screen.getByText('A report in the next 30 days lifts the reading.')).toBeInTheDocument();
    const todo = within(screen.getByRole('region', { name: 'What to do' }));
    expect(todo.getByRole('link', { name: volume })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(volume)}`,
    );
    const fooled = within(screen.getByRole('region', { name: 'Fields it fools' }));
    expect(fooled.getAllByRole('link').map((l) => l.textContent)).toEqual([
      volume,
      'feature.atr_ratio_5_20',
    ]);
  });

  it('links the playbooks it affects, with the fields they read', () => {
    render(<GuideSituation slug="earnings-gap" />);
    const playbooks = within(screen.getByRole('region', { name: 'Playbooks it affects' }));
    expect(playbooks.getByRole('link', { name: 'Breakout' })).toHaveAttribute(
      'href',
      '/guide/playbooks/breakout',
    );
    expect(playbooks.getByText(`reads ${volume}`)).toBeInTheDocument();
  });

  it('says so when no site screen reads a field it fools', () => {
    hooks.useGuideSituation.mockReturnValue(fakeQuery({ ...situation, playbooks: [] }));
    render(<GuideSituation slug="earnings-gap" />);
    expect(screen.getByText('No site screen reads a field it fools.')).toBeInTheDocument();
  });

  it('shows loading, an error with a retry, and an unknown situation', async () => {
    hooks.useGuideSituation.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideSituation slug="x" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideSituation.mockReturnValue(failed);
    rerender(<GuideSituation slug="x" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideSituation.mockReturnValue(fakeQuery(null));
    rerender(<GuideSituation slug="x" />);
    expect(screen.getByText('No such situation')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideSituation slug="earnings-gap" />);
    await expectNoA11yViolations(container);
  });
});

describe('GuideSituationsIndex', () => {
  it('lists every situation linked to its page with how many fields it fools', () => {
    render(<GuideSituationsIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Situations' })).toBeInTheDocument();
    const list = within(screen.getByRole('region', { name: 'Situations' }));
    expect(list.getByRole('link', { name: 'Pending takeover' })).toHaveAttribute(
      'href',
      '/guide/situations/pending-takeover',
    );
    expect(list.getByText('fools 12 fields')).toBeInTheDocument();
    expect(list.getByText('fools 1 field')).toBeInTheDocument();
  });

  it('shows loading, an error with a retry, and no situations', async () => {
    hooks.useGuideIndex.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<GuideSituationsIndex />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    rerender(<GuideSituationsIndex />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideIndex.mockReturnValue(fakeQuery({ sections: [], situations: [] }));
    rerender(<GuideSituationsIndex />);
    expect(screen.getByText('The Guide has no situations.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideSituationsIndex />);
    await expectNoA11yViolations(container);
  });
});
