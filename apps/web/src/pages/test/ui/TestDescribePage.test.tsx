import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TestDescribePage } from './TestDescribePage';

const probe = vi.hoisted(() => ({ id: '' }));

vi.mock('@/features/screener-builder', () => ({
  ScreenerBuilderProvider: ({ id, children }: { id: string; children: React.ReactNode }) => {
    probe.id = id;
    return <>{children}</>;
  },
}));
vi.mock('@/widgets/draft-bar', () => ({ DraftBar: () => <Text>draft bar</Text> }));
vi.mock('@/widgets/describe-screen', () => ({ DescribeScreen: () => <Text>describe</Text> }));
vi.mock('@/widgets/criteria-table', () => ({ CriteriaTable: () => <Text>criteria</Text> }));

describe('TestDescribePage', () => {
  it('lays the sentence out around one provider, under the steps, with a way to Expert', async () => {
    const onOpenExpert = vi.fn();
    render(<TestDescribePage id="my-vrp" onDeleted={vi.fn()} onOpenExpert={onOpenExpert} />);
    expect(probe.id).toBe('my-vrp');
    for (const text of ['draft bar', 'describe', 'criteria'])
      expect(screen.getByText(text)).toBeInTheDocument();
    const steps = screen.getByRole('navigation', { name: 'Test steps' });
    expect(steps).toHaveTextContent(/Start.*Describe it.*Result/);
    await userEvent.click(screen.getByRole('button', { name: 'Open in Expert' }));
    expect(onOpenExpert).toHaveBeenCalledOnce();
  });
});
