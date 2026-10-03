import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UiProvider } from './UiProvider';

describe('UiProvider', () => {
  it('applies theme, density and up/down palette to the document root', () => {
    render(
      <UiProvider theme="dark" density="comfortable" upDown="cvd">
        content
      </UiProvider>,
    );
    const root = document.documentElement;
    expect(root).toHaveAttribute('data-theme', 'dark');
    expect(root).toHaveAttribute('data-density', 'comfortable');
    expect(root).toHaveAttribute('data-updown', 'cvd');
  });

  it('leaves the theme to the system preference by default', () => {
    render(<UiProvider>content</UiProvider>);
    expect(document.documentElement).not.toHaveAttribute('data-theme');
    expect(document.documentElement).toHaveAttribute('data-density', 'compact');
  });
});
