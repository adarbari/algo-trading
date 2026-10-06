import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, unknownRegimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeIndicators } from './RegimeIndicators';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
}));

vi.mock('@/features/indicator-history', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    IndicatorHistory: ({
      indicator,
      window,
    }: {
      indicator: { key: string };
      window: { start: string; end: string };
    }) => <Text>{`history of ${indicator.key} from ${window.start} to ${window.end}`}</Text>,
  };
});

vi.mock('@/features/regime-explain', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    ExplainRegime: ({ card }: { card?: string }) => (
      <Button>{`Explain ${card ?? 'the regime'}`}</Button>
    ),
  };
});

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('RegimeIndicators', () => {
  it('lists the slow and the fast cards in their own lists', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { container } = render(<RegimeIndicators />);
    const slow = screen.getByRole('region', { name: 'Slow-moving warning signs' });
    const fast = screen.getByRole('region', { name: 'Fast-moving market signs' });
    expect(within(slow).getAllByRole('listitem')).toHaveLength(2);
    expect(within(fast).getAllByRole('listitem')).toHaveLength(1);
    expect(within(slow).getByText('Is the yield curve inverted?')).toBeVisible();
    expect(within(fast).getByText('Is fear rising?')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('opens a card to its why, history, lead time, false alarms and links', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(
      screen.getByText('An inverted curve has come before every recent recession.'),
    ).not.toBeVisible();
    await userEvent.setup().click(
      screen.getAllByRole('button', {
        name: /Why it matters, what it did before/,
      })[0] as HTMLElement,
    );
    expect(
      screen.getByText('An inverted curve has come before every recent recession.'),
    ).toBeVisible();
    expect(screen.getByText('2008: Inverted for 16 months before the fall.')).toBeVisible();
    expect(screen.getByText('Lead time: 6 to 24 months')).toBeVisible();
    expect(screen.getByText('False alarms: Few, but it can be early by two years.')).toBeVisible();
    expect(screen.getByRole('link', { name: /FRED: 10y minus 3m spread/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/series/T10Y3M',
    );
  });

  it('places each value on its range with the threshold marked and the rule in words', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    const curve = screen.getByRole('meter', { name: '10y minus 3m Treasury spread' });
    expect(curve).toHaveAttribute('aria-valuemin', '-1.5');
    expect(curve).toHaveAttribute('aria-valuemax', '3');
    expect(curve).toHaveAttribute('aria-valuetext', '0.42, off');
    expect(screen.getByText('On when below 0.00')).toBeVisible();
    const nfci = screen.getByRole('meter', { name: 'Chicago Fed NFCI' });
    expect(nfci).toHaveAttribute('aria-valuetext', '0.30, off');
    expect(screen.getByText('On when above 0.50')).toBeVisible();
  });

  it('writes how it is calculated with its terms linked', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.getByRole('link', { name: /10-year Treasury yield/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/series/DGS10',
    );
    expect(screen.getByText('The VIX divided by the 3-month VIX.')).toBeVisible();
  });

  it('names the exact series and cadence, the one in use first, and its provenance', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    const nfci = screen.getByRole('link', { name: /FRED NFCI/ });
    expect(nfci).toHaveAttribute('href', 'https://fred.stlouisfed.org/series/NFCI');
    const anfci = screen.getByRole('link', { name: /FRED ANFCI/ });
    expect(nfci.compareDocumentPosition(anfci) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/weekly, not used today/)).toBeVisible();
    expect(
      screen.getByText(
        /FRED NFCI: last observation .*released .*; before .* values are today's revised figures/,
      ),
    ).toBeVisible();
    expect(screen.getByText(/FRED T10Y3M: last observation .*released /)).toBeVisible();
    expect(screen.queryByText(/FRED T10Y3M: .*revised figures/)).toBeNull();
  });

  it('mounts the history chart only once its disclosure is opened, on the shared window', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.queryByText(/^history of /)).toBeNull();
    await userEvent
      .setup()
      .click(screen.getAllByRole('button', { name: 'Show history' })[0] as HTMLElement);
    expect(screen.getByText('history of curve_10y3m from 1971-01-01 to 2026-10-02')).toBeVisible();
    expect(screen.queryByText(/history of nfci/)).toBeNull();
  });

  it('marks a changed card and shows the reason of an UNKNOWN value', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.getByText(/Turned on this week/)).toBeInTheDocument();
    expect(screen.getByText(/Unknown: no market row for 2026-10-02/)).toBeVisible();
  });

  it('shows every card UNKNOWN with its reason when the regime is not computed', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.getAllByText(/Unknown: not stored for this session/)).toHaveLength(3);
    expect(
      screen.getAllByRole('img', { name: /: unknown\. not stored for this session/ }),
    ).toHaveLength(3);
    expect(screen.queryByRole('meter')).toBeNull();
  });

  it('is empty when nothing is stored, loading before the answer, an error on failure', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeIndicators />);
    expect(screen.getByText(/there are no warning signs to show/)).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeIndicators />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the warning signs');
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeIndicators />);
    expect(screen.getByText('The warning signs failed to load.')).toBeVisible();
  });

  it('offers to explain each card when the regime is computed, and not when it is not', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { unmount } = render(<RegimeIndicators />);
    expect(screen.getAllByRole('button', { name: /^Explain /, hidden: true })).toHaveLength(3);
    unmount();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.queryByRole('button', { name: /^Explain /, hidden: true })).toBeNull();
  });
});
