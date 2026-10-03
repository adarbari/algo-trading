import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UiProvider } from './UiProvider';

describe('UiProvider', () => {
  it('applies theme, density and up/down palette to the document root', () => {
    render(
      <UiProvider theme="light" density="comfortable" upDown="cvd">
        content
      </UiProvider>,
    );
    const root = document.documentElement;
    expect(root).toHaveAttribute('data-theme', 'light');
    expect(root).toHaveAttribute('data-density', 'comfortable');
    expect(root).toHaveAttribute('data-updown', 'cvd');
  });

  it('is dark and compact by default', () => {
    render(<UiProvider>content</UiProvider>);
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(document.documentElement).toHaveAttribute('data-density', 'compact');
    expect(document.documentElement).toHaveAttribute('data-updown', 'standard');
  });

  it('can follow the system preference', () => {
    render(<UiProvider theme="system">content</UiProvider>);
    expect(document.documentElement).toHaveAttribute('data-theme', 'system');
  });
});
