import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { STUDY_FIXTURE as STUDY } from '@/entities/event';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EventStudyPanel } from './EventStudyPanel';

const hooks = vi.hoisted(() => ({ useInstrumentEventStudy: vi.fn() }));

vi.mock('@/entities/event', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentEventStudy: hooks.useInstrumentEventStudy,
}));

stubElementSize();

beforeEach(() => {
  hooks.useInstrumentEventStudy.mockReturnValue(fakeQuery(STUDY));
});

describe('EventStudyPanel', () => {
  it('lists the events ahead, the ladder with its marked rung and the filings', async () => {
    const { container } = render(<EventStudyPanel symbol="AAPL" />);
    const ahead = screen.getByRole('grid', { name: 'Events ahead for AAPL' });
    expect(within(ahead).getAllByRole('row').slice(1)).toHaveLength(3);
    expect(within(ahead).getByText('Monthly expiry')).toBeInTheDocument();
    const ladder = screen.getByRole('table', { name: /AAPL expiries/ });
    expect(within(ladder).getAllByRole('row').length).toBeGreaterThan(2);
    const filings = screen.getByRole('grid', { name: 'AAPL filings list' });
    expect(within(filings).getByText('Results')).toBeInTheDocument();
    expect(within(filings).getByText('2.02, 9.01')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("names a fund's reference and opens it", async () => {
    hooks.useInstrumentEventStudy.mockReturnValue(
      fakeQuery({
        ...STUDY,
        reference: {
          instrumentId: 'EQ:N',
          symbol: 'NVDA',
          kind: 'single_stock',
          source: 'name_rule',
          status: 'LINKED',
        },
      }),
    );
    const onSelect = vi.fn();
    render(<EventStudyPanel symbol="NVDL" onSelectSymbol={onSelect} />);
    expect(screen.getByText('Tracks NVDA')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Open NVDA' }));
    expect(onSelect).toHaveBeenCalledWith('NVDA');
  });

  it('says every part that is not known, with the server reason', () => {
    hooks.useInstrumentEventStudy.mockReturnValue(
      fakeQuery({
        ...STUDY,
        ahead: [],
        filings: [],
        ladder: [],
        gaps: [
          {
            instrumentId: null,
            part: 'ladder',
            unknown: {
              code: 'NO_PARTITION',
              kind: 'SYSTEM',
              guideTerm: 'unavailable_system',
              kindText: 'not available because of a system error',
              cause: null,
              reason: null,
            },
          },
          {
            instrumentId: 'EQ:A',
            part: 'filings',
            unknown: {
              code: 'NOT_APPLICABLE',
              kind: 'NOT_APPLICABLE',
              guideTerm: 'unavailable_not_applicable',
              kindText: 'does not apply to this instrument',
              cause: null,
              reason: null,
            },
          },
        ],
      }),
    );
    render(<EventStudyPanel symbol="SPY" />);
    expect(
      screen.getByText('Expiry ladder: not available because of a system error'),
    ).toBeInTheDocument();
    expect(screen.getByText('Filings: does not apply to this instrument')).toBeInTheDocument();
    expect(screen.getByText('No dated events ahead for SPY.')).toBeInTheDocument();
  });

  it('says when the ticker is not in the snapshot, and when the read failed', () => {
    hooks.useInstrumentEventStudy.mockReturnValue(fakeQuery(null));
    const { unmount } = render(<EventStudyPanel symbol="ZZZZ" />);
    expect(screen.getAllByText(/ZZZZ is not in the reference snapshot/)).toHaveLength(2);
    unmount();
    hooks.useInstrumentEventStudy.mockReturnValue(
      fakeQuery(undefined, { isError: true, isPending: false }),
    );
    render(<EventStudyPanel symbol="AAPL" />);
    expect(screen.getByText('AAPL events failed to load.')).toBeInTheDocument();
  });
});
