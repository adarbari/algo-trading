import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, servedEntries } from '@/shared/lib/testing';

import { GuideHelpProvider } from '../model/navigation';
import { GuideHelp, type GuideHelpProps } from './GuideHelp';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);
const prose = (text: string) => ({ segments: [{ text, field: null }] });

const TERM = {
  guideTerm: {
    entry: {
      id: 'not_run',
      term: 'NOT_RUN',
      short: 'No run exists for the session being read.',
    },
    body: prose('A screener that has not run for the session has no hits, not zero hits.'),
    seeAlso: [],
  },
};

const START = {
  guideStartPage: {
    entry: {
      id: 'read_a_result',
      order: 2,
      title: 'Read a screen result',
      summary: 'What a hit, a near miss and a reject mean.',
    },
    sections: [
      { title: 'A hit', body: prose('A hit passed every hard rule.') },
      { title: 'A near miss', body: prose('Second section, only on the full page.') },
    ],
    links: [],
  },
};

function setup(entry: GuideHelpProps['entry'], navigate = vi.fn()) {
  const view = render(
    <TestQueryProvider>
      <GuideHelpProvider navigate={navigate}>
        <GuideHelp entry={entry} />
      </GuideHelpProvider>
    </TestQueryProvider>,
  );
  return { ...view, navigate };
}

/** The button once the read arrived: it gains its hover summary, which replaces the element. */
async function summarised(name: RegExp) {
  await waitFor(() => {
    expect(screen.getByRole('button', { name })).toHaveAttribute('aria-describedby');
  });
  return screen.getByRole('button', { name });
}

beforeEach(() => {
  GQL.mockReset();
});

describe('GuideHelp for a glossary term', () => {
  beforeEach(() => {
    GQL.mockResolvedValue(servedEntries(TERM));
  });

  it('opens the term: its one-sentence definition and its body, with the hover being the short line', async () => {
    const { container } = setup({ kind: 'term', id: 'not_run' });
    const button = await summarised(/^What is NOT_RUN\?$/);
    await userEvent.hover(button);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'No run exists for the session being read.',
    );
    await userEvent.click(button);
    const drawer = await screen.findByRole('dialog', { name: 'NOT_RUN' });
    expect(within(drawer).getByText('No run exists for the session being read.')).toBeVisible();
    expect(within(drawer).getByText(/has no hits, not zero hits/)).toBeVisible();
    await expectNoA11yViolations(container);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ refs: [{ kind: 'TERM', id: 'not_run' }] });
  });

  it('opens the full glossary page through the app navigation', async () => {
    const { navigate } = setup({ kind: 'term', id: 'not_run' });
    await userEvent.click(await summarised(/^What is NOT_RUN\?$/));
    await userEvent.click(await screen.findByRole('button', { name: 'Open full page' }));
    expect(navigate).toHaveBeenCalledWith('/guide/glossary/not_run');
  });

  it('says so when the Guide has no such term', async () => {
    GQL.mockResolvedValue(servedEntries({ guideTerm: null }));
    setup({ kind: 'term', id: 'nope' });
    await userEvent.click(await screen.findByRole('button', { name: /^What is/ }));
    expect(await screen.findByText(/no entry for this term yet/)).toBeVisible();
  });
});

describe('GuideHelp for a Start here page', () => {
  beforeEach(() => {
    GQL.mockResolvedValue(servedEntries(START));
  });

  it('opens the summary and the first section only', async () => {
    const { container } = setup({ kind: 'start', id: 'read_a_result' });
    await userEvent.click(await summarised(/^How to: Read a screen result$/));
    const drawer = await screen.findByRole('dialog', { name: 'Read a screen result' });
    expect(within(drawer).getByText('What a hit, a near miss and a reject mean.')).toBeVisible();
    expect(within(drawer).getByRole('heading', { level: 3, name: 'A hit' })).toBeVisible();
    expect(within(drawer).getByText('A hit passed every hard rule.')).toBeVisible();
    expect(within(drawer).queryByText(/only on the full page/)).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('opens the full page through the app navigation', async () => {
    const { navigate } = setup({ kind: 'start', id: 'read_a_result' });
    await userEvent.click(await summarised(/^How to:/));
    await userEvent.click(await screen.findByRole('button', { name: 'Open full page' }));
    expect(navigate).toHaveBeenCalledWith('/guide/start/read_a_result');
  });
});
