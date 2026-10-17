import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartJoin } from '../PartJoin';
import { PartList } from './PartList';

const joinLabels = { joinedByLabel: 'joined by', readAsLabel: 'read as' };

describe('PartList', () => {
  it('keeps the callers keys, so a reorder keeps each card mounted', () => {
    const { rerender } = render(
      <PartList aria-label="Parts">
        <p key="a">first</p>
        <p key="b">second</p>
      </PartList>,
    );
    const first = screen.getByText('first');
    rerender(
      <PartList aria-label="Parts">
        <p key="b">second</p>
        <p key="a">first</p>
      </PartList>,
    );
    expect(screen.getByText('first')).toBe(first);
  });

  it('is a named ordered list with one item per card', async () => {
    const { container } = render(
      <PartList aria-label="Parts">
        <p>first</p>
        <p>second</p>
      </PartList>,
    );
    expect(screen.getByRole('list', { name: 'Parts' }).tagName).toBe('OL');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    await expectNoA11yViolations(container);
  });

  it('places a connector inside the next cards item, so items still count parts', async () => {
    const { container } = render(
      <PartList aria-label="Parts">
        <p>first</p>
        <PartJoin join="and_not" label="but not" words="except" {...joinLabels} />
        <p>second</p>
      </PartList>,
    );
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[1]).toHaveTextContent('joined byexcept, read asbut not');
    expect(items[0]).not.toHaveTextContent('joined by');
    await expectNoA11yViolations(container);
  });

  it('attaches a leading connector to the first card', () => {
    render(
      <PartList aria-label="Parts">
        <PartJoin join="or" label="or" {...joinLabels} />
        <p>first</p>
      </PartList>,
    );
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent('joined byor');
  });

  it('drops a trailing connector and warns in development', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(
      <PartList aria-label="Parts">
        <p>first</p>
        <PartJoin join="or" label="or" {...joinLabels} />
      </PartList>,
    );
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.queryByText('joined by')).toBeNull();
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
