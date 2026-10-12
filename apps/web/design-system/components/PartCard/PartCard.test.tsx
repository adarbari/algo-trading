import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartList } from '../PartList';
import { PartCard, type PartCardProps } from './PartCard';

const props: PartCardProps = {
  kind: 'applied',
  kindLabel: 'applied',
  words: 'stocks over $5',
  readingLabel: 'We read this as',
  reading: 'Price above $5.',
  checkReadingLabel: 'check this reading',
  retryLabel: 'Try again',
  editedLabel: 'edited',
  redraftingLabel: 'Redrafting this part',
  rows: <p>close above 5</p>,
  actions: <button type="button">Retype this part</button>,
};

describe('PartCard', () => {
  it('quotes the words, the kind, the reading, rows and actions', () => {
    render(<PartCard {...props} />);
    expect(screen.getByText('stocks over $5').tagName).toBe('MARK');
    expect(screen.getByText('applied')).toBeInTheDocument();
    expect(screen.getByText(/We read this as/)).toBeInTheDocument();
    expect(screen.getByText('close above 5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retype this part' })).toBeInTheDocument();
    expect(screen.queryByText('check this reading')).toBeNull();
  });

  it('shows the muted note for a reading the model did not write', () => {
    render(<PartCard {...props} readingSource="server" />);
    expect(screen.getByText('check this reading')).toBeInTheDocument();
  });

  it('shows a kept card by its title, with no quoted words', () => {
    const { container } = render(
      <PartCard
        {...props}
        kind="kept"
        kindLabel="kept"
        words={undefined}
        title="Kept from your screen"
      />,
    );
    expect(container.querySelector('mark')).toBeNull();
    expect(screen.getByText('Kept from your screen')).toBeInTheDocument();
  });

  it('redrafts this card only: words stay, body is busy', () => {
    render(<PartCard {...props} state="redrafting" />);
    expect(screen.getByText('stocks over $5')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'stocks over $5' })).toHaveAttribute(
      'aria-busy',
      'true',
    );
    expect(screen.queryByText('close above 5')).toBeNull();
  });

  it('offers an inline retry on error', () => {
    const onRetry = vi.fn();
    render(
      <PartCard {...props} state="error" errorMessage="Could not redraft." onRetry={onRetry} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Could not redraft.');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('marks edited rows', () => {
    render(<PartCard {...props} edited />);
    expect(screen.getByText('edited')).toBeInTheDocument();
  });

  it('retypes with Apply and Cancel as callbacks', () => {
    const retype = {
      value: 'new words',
      onValueChange: vi.fn(),
      onApply: vi.fn(),
      onCancel: vi.fn(),
      inputLabel: 'Retype',
      applyLabel: 'Apply',
      cancelLabel: 'Cancel',
    };
    render(<PartCard {...props} retype={retype} />);
    fireEvent.change(screen.getByLabelText('Retype'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(retype.onValueChange).toHaveBeenCalledWith('x');
    expect(retype.onApply).toHaveBeenCalledOnce();
    expect(retype.onCancel).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations in any state, inside a list', async () => {
    const { container } = render(
      <PartList aria-label="Parts">
        <PartCard {...props} />
        <PartCard
          {...props}
          kind="not-understood"
          kindLabel="not understood"
          reading={undefined}
          rows={undefined}
        />
        <PartCard
          {...props}
          kind="kept"
          kindLabel="kept"
          words={undefined}
          title="Kept from your screen"
        />
        <PartCard {...props} words="one" state="redrafting" />
        <PartCard
          {...props}
          words="two"
          state="error"
          errorMessage="Failed."
          onRetry={() => undefined}
        />
        <PartCard {...props} words="three" state="disabled" edited readingSource="server" />
      </PartList>,
    );
    expect(screen.getAllByRole('listitem')).toHaveLength(6);
    await expectNoA11yViolations(container);
  });
});
