import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Breakpoint } from '../tokens';
import { useNarrow } from './useNarrow';

/** Every ResizeObserver created while the test runs, so a test can report a width. */
const callbacks: ResizeObserverCallback[] = [];

function observeWidths() {
  class FakeObserver {
    constructor(callback: ResizeObserverCallback) {
      callbacks.push(callback);
    }
    observe() {}
    disconnect() {}
    unobserve() {}
  }
  vi.stubGlobal('ResizeObserver', FakeObserver);
}

function report(width: number) {
  act(() => {
    callbacks.forEach((callback) => {
      callback([{ contentRect: { width } } as ResizeObserverEntry], {} as ResizeObserver);
    });
  });
}

function Probe({ size }: { size?: Breakpoint }) {
  const [ref, narrow] = useNarrow(size);
  return <div ref={ref}>{narrow ? 'narrow' : 'wide'}</div>;
}

describe('useNarrow', () => {
  afterEach(() => {
    callbacks.length = 0;
    vi.unstubAllGlobals();
  });

  it('guesses from the viewport before the first measurement', () => {
    vi.stubGlobal('innerWidth', 375);
    render(<Probe />);
    expect(screen.getByText('narrow')).toBeInTheDocument();
  });

  it('follows the measured width against the breakpoint token', () => {
    vi.stubGlobal('innerWidth', 1400);
    observeWidths();
    render(<Probe size="md" />);
    expect(screen.getByText('wide')).toBeInTheDocument();
    report(700);
    expect(screen.getByText('narrow')).toBeInTheDocument();
    report(720);
    expect(screen.getByText('wide')).toBeInTheDocument();
  });

  it('keeps the last answer while the element has no width', () => {
    vi.stubGlobal('innerWidth', 375);
    observeWidths();
    render(<Probe />);
    report(0);
    expect(screen.getByText('narrow')).toBeInTheDocument();
  });
});
