import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { setupStateLabel, setupStateTerm, setupStateTone } from '../model/edges';

import { SetupStateChip } from './SetupStateChip';

describe('SetupStateChip', () => {
  it('words each state and gives it its own Guide term and tone', () => {
    expect(['ON', 'OFF', 'PAUSED', 'UNKNOWN'].map(setupStateLabel)).toEqual([
      'On',
      'Off',
      'Paused',
      'Unknown',
    ]);
    expect(setupStateTerm('PAUSED')).toBe('setup_state_paused');
    expect(setupStateTone('ON')).toBe('positive');
    expect(setupStateTone('PAUSED')).toBe('warning');
    expect(setupStateTone('NEW_CODE')).toBe('neutral');
  });

  it('draws the chip and the caller’s help button, and nothing without a state', () => {
    const { rerender } = render(
      <SetupStateChip
        state={{ state: 'PAUSED', reason: 'gate closed' }}
        help={<Text>help</Text>}
      />,
    );
    expect(screen.getByText('Paused')).toBeInTheDocument();
    expect(screen.getByText('help')).toBeInTheDocument();
    rerender(<SetupStateChip state={null} help={<Text>help</Text>} />);
    expect(screen.queryByText('Paused')).not.toBeInTheDocument();
    expect(screen.queryByText('help')).not.toBeInTheDocument();
  });
});
