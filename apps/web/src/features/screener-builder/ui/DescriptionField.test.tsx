import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DescriptionField } from './DescriptionField';

describe('DescriptionField', () => {
  it('counts the characters and previews the list row only with text', async () => {
    const { container, rerender } = render(
      <DescriptionField name="my-vrp" value="" onChange={vi.fn()} />,
    );
    expect(screen.getByText('0 / 140')).toBeInTheDocument();
    expect(screen.queryByText('On the Screeners list')).toBeNull();
    rerender(<DescriptionField name="my-vrp" value="Cheap names" onChange={vi.fn()} />);
    expect(screen.getByText('11 / 140')).toBeInTheDocument();
    expect(screen.getByText('Cheap names', { selector: 'p' }).parentElement).toHaveAttribute(
      'title',
      'Cheap names',
    ); // the list row's LineClamp
    await expectNoA11yViolations(container);
  });

  it('strips newlines to one line and cuts at 140 characters', async () => {
    const onChange = vi.fn();
    render(<DescriptionField name="a" value="" onChange={onChange} />);
    await userEvent.click(screen.getByRole('textbox'));
    await userEvent.paste('a\nb');
    expect(onChange).toHaveBeenLastCalledWith('a b');
    await userEvent.paste('x'.repeat(200));
    expect(onChange.mock.lastCall?.[0]).toHaveLength(140);
  });

  it('shows the error inline', () => {
    render(<DescriptionField name="a" value="" onChange={vi.fn()} error="Add one" />);
    expect(screen.getByText('Add one')).toBeInTheDocument();
  });
});
