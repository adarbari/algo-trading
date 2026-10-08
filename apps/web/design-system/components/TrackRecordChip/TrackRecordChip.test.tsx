import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TrackRecordChip } from './TrackRecordChip';

describe('TrackRecordChip', () => {
  it('says the state in words', () => {
    const { rerender } = render(<TrackRecordChip status="evidenced" />);
    expect(screen.getByText('Evidenced')).toBeInTheDocument();
    rerender(<TrackRecordChip status="not-run" />);
    expect(screen.getByText('Not run')).toBeInTheDocument();
    rerender(<TrackRecordChip status="candidate" sessions={42} />);
    expect(screen.getByText('Candidate · 42 sessions')).toBeInTheDocument();
    rerender(<TrackRecordChip status="candidate" sessions={1} />);
    expect(screen.getByText('Candidate · 1 session')).toBeInTheDocument();
  });

  it('renders nothing for an exploratory record, whatever its status', () => {
    const { container } = render(<TrackRecordChip status="evidenced" exploratory />);
    expect(container).toBeEmptyDOMElement();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<TrackRecordChip status="candidate" sessions={3} />);
    await expectNoA11yViolations(container);
  });
});
