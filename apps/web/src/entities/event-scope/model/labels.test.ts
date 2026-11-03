import { describe, expect, it } from 'vitest';

import { scopeName } from './fixtures';
import { addedBy, isTicker, reasonLabel, sourceLabel } from './labels';

describe('labels', () => {
  it('words the reasons the server sends and passes an unknown one through', () => {
    expect(reasonLabel('tier')).toBe('Put tier');
    expect(reasonLabel('something_new')).toBe('something_new');
  });

  it('names the source', () => {
    expect(sourceLabel('site')).toBe('Site file');
    expect(sourceLabel('admin')).toBe('Admin');
  });

  it('says who added an admin entry, and nothing for the site file', () => {
    expect(addedBy(scopeName())).toBe('');
    expect(
      addedBy(scopeName({ source: 'admin', by: 'ana', at: '2026-10-25T09:00:00+00:00' })),
    ).toBe('ana, 2026-10-25');
  });

  it('accepts tickers with a dot or dash and refuses spaces and long text', () => {
    expect(isTicker('BRK.B')).toBe(true);
    expect(isTicker(' aapl ')).toBe(true);
    expect(isTicker('A B')).toBe(false);
    expect(isTicker('')).toBe(false);
    expect(isTicker('ABCDEFGHIJKLM')).toBe(false);
  });
});
