import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OPTION_SETUP_FIXTURE, OPTION_SETUP_HIDDEN_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SetupOptionRecord } from './SetupOptionRecord';

vi.mock('@/entities/availability', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    UnknownNote: ({ unknown }: { unknown: { kindText: string } }) => (
      <Text>{unknown.kindText}</Text>
    ),
  };
});
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    Labelled: ({ text, help }: { text: string; help: string }) => (
      <Text>{`${text} (${help})`}</Text>
    ),
  };
});

const evidence = OPTION_SETUP_FIXTURE.evidence;
const hidden = OPTION_SETUP_HIDDEN_FIXTURE.evidence;
if (evidence == null || hidden == null) throw new Error('the fixtures carry evidence');

describe('SetupOptionRecord', () => {
  it('shows the strip labelled backtested, how sure, the costs, the stress windows and the years', async () => {
    const { container } = render(<SetupOptionRecord evidence={evidence} />);
    expect(screen.getByText(/Backtested \(hypothetical\)/)).toBeInTheDocument();
    expect(screen.getByText(/A typical trade/)).toBeInTheDocument();
    expect(screen.getByText('from −0.4% to 2.1%')).toBeInTheDocument();
    expect(screen.getByText('the worst 5 of 100 trades')).toBeInTheDocument();
    expect(screen.getByText('72 of 100 trades')).toBeInTheDocument();
    expect(screen.getByText('At the middle price')).toBeInTheDocument();
    expect(screen.getByText('At the full spread')).toBeInTheDocument();
    expect(screen.getByText('No trade was open')).toBeInTheDocument();
    expect(screen.getByText(/−9\.2% worst, of 6 open/)).toBeInTheDocument();
    expect(screen.getByText('2024')).toBeInTheDocument();
    expect(screen.getByText('help option_by_year')).toBeInTheDocument();
    expect(screen.getByText('help option_how_sure')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows only the server reason where history-derived evidence is withheld', () => {
    render(<SetupOptionRecord evidence={hidden} />);
    expect(screen.getByText('Not available to your account')).toBeInTheDocument();
    expect(screen.queryByText(/A typical trade/)).not.toBeInTheDocument();
  });

  it('flags a setup read only in-sample and says why stress is empty', () => {
    render(
      <SetupOptionRecord
        evidence={{
          ...evidence,
          inSampleOnly: true,
          stress: [],
          stressUnknown: {
            code: 'NOT_COVERED',
            kind: 'NOT_COVERED',
            guideTerm: 'unavailable_not_covered',
            kindText: 'Outside the stored history',
          },
        }}
      />,
    );
    expect(screen.getByText('In-sample only')).toBeInTheDocument();
    expect(screen.getByText('Outside the stored history')).toBeInTheDocument();
  });
});
