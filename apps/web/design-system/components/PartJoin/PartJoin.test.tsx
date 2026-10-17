import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartJoin } from './PartJoin';

const labels = { joinedByLabel: 'joined by', readAsLabel: 'read as' };

describe('PartJoin', () => {
  it('reads the traders word, then the logic, in order', async () => {
    const { container } = render(
      <PartJoin join="and_not" label="but not" words="except" {...labels} />,
    );
    expect(container.textContent).toBe('joined byexcept, read asbut not');
    await expectNoA11yViolations(container);
  });

  it('drops a word that only repeats the label, or no word at all', () => {
    const { container, rerender } = render(
      <PartJoin join="or" label="or" words="Or" {...labels} />,
    );
    expect(container.textContent).toBe('joined byor');
    rerender(<PartJoin join="and" label="and" {...labels} />);
    expect(container.textContent).toBe('joined byand');
  });

  it('tones or and but-not apart from and', () => {
    const { container, rerender } = render(<PartJoin join="and" label="and" {...labels} />);
    const tone = () => container.firstElementChild?.getAttribute('data-join');
    expect(tone()).toBe('and');
    rerender(<PartJoin join="or" label="or" {...labels} />);
    expect(tone()).toBe('or');
    rerender(<PartJoin join="and_not" label="but not" {...labels} />);
    expect(tone()).toBe('and_not');
  });
});
