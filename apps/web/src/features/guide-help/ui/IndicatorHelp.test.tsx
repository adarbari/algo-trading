import { render, screen, waitFor, within } from '@testing-library/react';
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
  guideIndicator: {
    key: 'curve_10y3m',
    plainName: 'Is the yield curve inverted?',
    technicalName: '10y minus 3m Treasury spread',
    pace: 'slow',
    summary: prose('Short rates above long ones.'),
    whyItMatters: prose('It has come before every recent recession.'),
    whatOnMeans: prose('The spread is below zero.'),
    leadTime: prose('6 to 24 months.'),
    trackRecord: prose('Few false alarms.'),
    before: [],
    how: [{ text: 'The 10y minus the 3m.', url: null }],
    feature: 'market.regime_indicators@v1.curve_10y3m',
    sources: [],
  },
};

/** The button once the read arrived: it gains its hover summary, which replaces the element. */
async function summarised() {
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /^What is / })).toHaveAttribute('aria-describedby');
  });
  return screen.getByRole('button', { name: /^What is / });
}

function setup(navigate = vi.fn()) {
  const view = render(
    <TestQueryProvider>
      <GuideHelpProvider navigate={navigate}>
        <GuideHelp entry={{ kind: 'indicator', id: 'curve_10y3m' }} />
      </GuideHelpProvider>
    </TestQueryProvider>,
  );
  return { ...view, navigate };
}

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue(SERVED);
});

describe('GuideHelp for a regime indicator', () => {
  it('opens its summary, why it matters, when it is on, lead time and track record', async () => {
    const { container } = setup();
    await userEvent.click(await summarised());
    const drawer = await screen.findByRole('dialog');
    expect(drawer).toHaveTextContent('10y minus 3m Treasury spread');
    expect(within(drawer).getByText('Short rates above long ones.')).toBeVisible();
    expect(within(drawer).getByRole('heading', { level: 3, name: 'Why it matters' })).toBeVisible();
    expect(within(drawer).getByText('It has come before every recent recession.')).toBeVisible();
    expect(within(drawer).getByText('The spread is below zero.')).toBeVisible();
    expect(within(drawer).getByText('6 to 24 months.')).toBeVisible();
    expect(within(drawer).getByText('Few false alarms.')).toBeVisible();
    await expectNoA11yViolations(container);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ key: 'curve_10y3m' });
  });

  it('opens the full page through the app navigation', async () => {
    const { navigate } = setup();
    await userEvent.click(await summarised());
    await userEvent.click(await screen.findByRole('button', { name: 'Open full page' }));
    expect(navigate).toHaveBeenCalledWith('/guide/regime/indicators/curve_10y3m');
  });

  it('says so when the Guide has no entry', async () => {
    GQL.mockResolvedValue({ guideIndicator: null });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: /^What is / }));
    expect(await screen.findByText(/no entry for this warning sign yet/)).toBeVisible();
  });
});
