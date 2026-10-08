import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SearchDialog, type SearchDialogProps } from './SearchDialog';

const GROUPS: SearchDialogProps['groups'] = [
  {
    id: 'field',
    title: 'Fields',
    items: [
      {
        id: 'a',
        title: 'rel_volume',
        snippet: 'Volume over its average.',
        href: '/guide/fields/a',
      },
      { id: 'b', title: 'adv_usd_20d', href: '/guide/fields/b' },
    ],
  },
  {
    id: 'term',
    title: 'Glossary',
    items: [{ id: 'c', title: 'LIQUIDITY_RISK', href: '/guide/glossary/c' }],
  },
];

function setup(props: Partial<SearchDialogProps> = {}) {
  const onSelect = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <SearchDialog
      open
      onOpenChange={onOpenChange}
      title="Search the Guide"
      query="vol"
      onQueryChange={() => undefined}
      groups={GROUPS}
      onSelect={onSelect}
      {...props}
    />,
  );
  return { onSelect, onOpenChange };
}

describe('SearchDialog', () => {
  it('shows the results in groups, each a link with its snippet', () => {
    setup();
    expect(screen.getByRole('dialog', { name: 'Search the Guide' })).toBeInTheDocument();
    const fields = screen.getByRole('region', { name: 'Fields' });
    expect(fields).toHaveTextContent('Volume over its average.');
    expect(screen.getByRole('link', { name: /rel_volume/ })).toHaveAttribute(
      'href',
      '/guide/fields/a',
    );
    expect(screen.getByRole('region', { name: 'Glossary' })).toBeInTheDocument();
  });

  it('moves focus down and up the results and back to the box', async () => {
    setup();
    const user = userEvent.setup();
    const box = screen.getByRole('searchbox', { name: 'Search the Guide' });
    await waitFor(() => {
      expect(box).toHaveFocus();
    });
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('link', { name: /rel_volume/ })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('link', { name: /LIQUIDITY_RISK/ })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('link', { name: /LIQUIDITY_RISK/ })).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    await user.keyboard('{ArrowUp}');
    await user.keyboard('{ArrowUp}');
    expect(box).toHaveFocus();
  });

  it('opens the first result on Enter in the box and the focused one on Enter', async () => {
    const { onSelect } = setup();
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByRole('searchbox')).toHaveFocus();
    });
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith(GROUPS[0]?.items[0]);
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith(GROUPS[0]?.items[1]);
  });

  it('holds Enter while the results are on their way and opens the first when they land', async () => {
    const onSelect = vi.fn();
    const props = {
      open: true,
      onOpenChange: () => undefined,
      title: 'Search',
      query: 'vol',
      onQueryChange: () => undefined,
      onSelect,
    };
    const { rerender } = render(<SearchDialog {...props} groups={[]} loading />);
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByRole('searchbox')).toHaveFocus();
    });
    await user.keyboard('{Enter}');
    expect(onSelect).not.toHaveBeenCalled();
    rerender(<SearchDialog {...props} groups={GROUPS} />);
    expect(onSelect).toHaveBeenCalledWith(GROUPS[0]?.items[0]);
  });

  it('selects on a plain click but leaves a modified click to the browser', async () => {
    const { onSelect } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByRole('link', { name: /adv_usd_20d/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    await user.keyboard('{Control>}');
    await user.click(screen.getByRole('link', { name: /adv_usd_20d/ }));
    await user.keyboard('{/Control}');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('shows the hint before anything is typed', () => {
    setup({ query: '', groups: [], hint: 'Type a field name.' });
    expect(screen.getByText('Type a field name.')).toBeInTheDocument();
  });

  it('says when nothing matches, while reading and when it failed', () => {
    const { rerender } = render(
      <SearchDialog
        open
        onOpenChange={() => undefined}
        title="Search"
        query="zzz"
        onQueryChange={() => undefined}
        groups={[]}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByText('Nothing matches “zzz”.')).toBeInTheDocument();
    rerender(
      <SearchDialog
        open
        onOpenChange={() => undefined}
        title="Search"
        query="zzz"
        onQueryChange={() => undefined}
        groups={[]}
        loading
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    rerender(
      <SearchDialog
        open
        onOpenChange={() => undefined}
        title="Search"
        query="zzz"
        onQueryChange={() => undefined}
        groups={[]}
        error
        onRetry={() => undefined}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('The search failed.');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    setup();
    await expectNoA11yViolations(document.body);
  });
});
