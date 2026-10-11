import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LazySection } from './LazySection';

/** A fake IntersectionObserver the test can fire. */
function stubObserver() {
  const state = { callback: undefined as IntersectionObserverCallback | undefined, observed: 0 };
  class Fake {
    constructor(callback: IntersectionObserverCallback) {
      state.callback = callback;
    }
    observe = () => {
      state.observed += 1;
    };
    disconnect = vi.fn();
  }
  vi.stubGlobal('IntersectionObserver', Fake);
  return state;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LazySection', () => {
  it('renders the children at once when IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    render(<LazySection label="Evidence curve">content</LazySection>);
    expect(screen.getByText('content')).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('holds a busy placeholder until the section nears the viewport, then keeps the children', async () => {
    const state = stubObserver();
    const { container } = render(
      <LazySection label="Evidence curve" minBlockSize="lg">
        content
      </LazySection>,
    );
    expect(screen.queryByText('content')).toBeNull();
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveTextContent('Loading Evidence curve');
    expect(container.querySelector('[data-size="lg"]')).not.toBeNull();
    await expectNoA11yViolations(container);
    expect(state.observed).toBe(1);

    act(() => {
      state.callback?.(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    });
    expect(screen.queryByText('content')).toBeNull();
    act(() => {
      state.callback?.(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    });
    expect(screen.getByText('content')).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
  });
});
