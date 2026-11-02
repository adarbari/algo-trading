import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OPTION_SETUP_FIXTURE } from '@/entities/edge';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SetupOptionRules } from './SetupOptionRules';

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
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

describe('SetupOptionRules', () => {
  it('shows the declared position, one row per part, each with its help', async () => {
    const { container } = render(
      <SetupOptionRules name="Weekly puts" setup={OPTION_SETUP_FIXTURE} />,
    );
    expect(screen.getByText('Decides')).toBeInTheDocument();
    expect(screen.getByText('1 put, 0.30 delta, 30 days')).toBeInTheDocument();
    expect(screen.getByText('help option_rule_leg')).toBeInTheDocument();
    expect(screen.getByText('help option_rules_position')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('says why there are no rules when the server could not give them', () => {
    render(
      <SetupOptionRules
        name="Weekly puts"
        setup={{
          ...OPTION_SETUP_FIXTURE,
          rules: null,
          rulesUnknown: {
            code: 'NOT_APPLICABLE',
            kind: 'NOT_APPLICABLE',
            guideTerm: 'unavailable_not_applicable',
            kindText: 'Does not apply',
          },
        }}
      />,
    );
    expect(screen.getByText('Does not apply')).toBeInTheDocument();
    expect(screen.queryByText('Decides')).not.toBeInTheDocument();
  });
});
