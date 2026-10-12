import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AdminFeatureRequestsPage } from './AdminFeatureRequestsPage';

vi.mock('@/widgets/feature-request-list', () => ({ FeatureRequestList: () => '[list]' }));

describe('AdminFeatureRequestsPage', () => {
  it('lays out the list under its heading', () => {
    render(<AdminFeatureRequestsPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Feature requests' })).toBeInTheDocument();
    expect(document.body).toHaveTextContent('[list]');
  });
});
