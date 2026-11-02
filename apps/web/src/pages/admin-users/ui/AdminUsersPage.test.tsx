import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AdminUsersPage } from './AdminUsersPage';

vi.mock('@/widgets/user-list', () => ({ UserList: () => '[people]' }));

describe('AdminUsersPage', () => {
  it('lays out the heading and the people', () => {
    render(<AdminUsersPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Users' })).toBeInTheDocument();
    expect(document.body).toHaveTextContent('[people]');
  });
});
