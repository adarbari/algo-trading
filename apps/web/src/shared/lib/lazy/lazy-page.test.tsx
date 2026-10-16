import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { lazyPage } from './lazy-page';

const Hello = ({ who }: { who: string }) => `hello ${who}`;

describe('lazyPage', () => {
  it('renders the page in the first commit once its chunk is preloaded (no Suspense)', async () => {
    const Page = lazyPage(() => Promise.resolve({ Hello }), 'Hello');
    await Page.preload();
    // No Suspense boundary: a suspending lazy would throw here, and React 19 holds a
    // suspended reveal for 300 ms.
    render(<Page who="world" />);
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });

  it('loads the module once however often it is preloaded', async () => {
    let calls = 0;
    const Page = lazyPage(() => Promise.resolve({ calls: ++calls, Hello }), 'Hello');
    await Promise.all([Page.preload(), Page.preload()]);
    expect(calls).toBe(1);
  });
});
