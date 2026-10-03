import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlaceholderPage } from './PlaceholderPage';

describe('PlaceholderPage', () => {
  it('names the section and what it is for', () => {
    render(<PlaceholderPage title="Explore" summary="One page for instruments." />);
    expect(screen.getByRole('heading', { level: 1, name: 'Explore' })).toBeInTheDocument();
    expect(screen.getByText('One page for instruments.')).toBeInTheDocument();
  });
});
