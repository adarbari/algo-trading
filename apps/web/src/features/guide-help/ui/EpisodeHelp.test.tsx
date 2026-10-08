import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { GuideHelpProvider } from '../model/navigation';
import { GuideHelp } from './GuideHelp';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);
const prose = (text: string) => ({ segments: [{ text, field: null }] });
const SERVED = {
  guideEpisode: {
    episode: {
      key: 'gfc_2007',
      name: 'Global financial crisis, 2007-09',
      kind: 'recession',
      peak: '2007-10-09',
      trough: '2009-03-09',
      recovered: '2013-03-28',
      spxDrawdown: -0.57,
      nasdaqDrawdown: -0.55,
      recession: true,
      nberStart: '2007-12-01',
      nberEnd: '2009-06-01',
      knownFrom: '2009-03-09',
    },
    cause: prose('A housing bust spread through the banks.'),
    notes: prose(''),
    indicators: [],
  },
};

function setup(navigate = vi.fn()) {
  const view = render(
    <TestQueryProvider>
      <GuideHelpProvider navigate={navigate}>
        <GuideHelp entry={{ kind: 'episode', id: 'gfc_2007' }} />
      </GuideHelpProvider>
    </TestQueryProvider>,
  );
  return { ...view, navigate };
}

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue(SERVED);
});

describe('GuideHelp for a market fall', () => {
  it('opens its name, kind, dates, drawdowns and cause', async () => {
    const { container } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /^About / }));
    const drawer = await screen.findByRole('dialog');
    expect(
      await within(drawer).findByText('A housing bust spread through the banks.'),
    ).toBeVisible();
    expect(drawer).toHaveTextContent('Global financial crisis, 2007-09');
    expect(drawer).toHaveAccessibleDescription(/Recession bear market/);
    const facts = within(drawer).getByText('S&P 500 fall');
    expect(facts.closest('div')).toHaveTextContent(/[-−]57%/);
    expect(within(drawer).getByText('Recovered').closest('div')).toHaveTextContent(/2013/);
    await expectNoA11yViolations(container);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ slug: 'gfc_2007' });
  });

  it('says a fall that has not recovered has not, and opens the full page', async () => {
    GQL.mockResolvedValue({
      guideEpisode: {
        ...SERVED.guideEpisode,
        episode: { ...SERVED.guideEpisode.episode, recovered: null },
      },
    });
    const { navigate } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /^About / }));
    const drawer = await screen.findByRole('dialog');
    expect((await within(drawer).findByText('Recovered')).closest('div')).toHaveTextContent(
      'Not yet',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Open full page' }));
    expect(navigate).toHaveBeenCalledWith('/guide/regime/episodes/gfc_2007');
  });
});
