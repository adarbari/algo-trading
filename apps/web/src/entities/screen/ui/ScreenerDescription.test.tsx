import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScreenerDescription } from './ScreenerDescription';

describe('ScreenerDescription', () => {
  it('shows the description clamped to two lines', () => {
    render(<ScreenerDescription description="Cheap names with rising margins" />);
    expect(screen.getByText('Cheap names with rising margins').parentElement).toHaveAttribute(
      'title',
      'Cheap names with rising margins',
    );
  });
});
