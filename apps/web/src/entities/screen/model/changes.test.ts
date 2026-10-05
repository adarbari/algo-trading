import { describe, expect, it } from 'vitest';

import { previewChanges } from './changes';

const row = (symbol: string | null, decision: string) => ({ symbol, decision });

describe('previewChanges', () => {
  it('lists who enters and who leaves the picks, by symbol', () => {
    const saved = [row('AAPL', 'QUALIFIED'), row('SOXS', 'WATCH'), row('KO', 'REJECT')];
    const preview = [row('AAPL', 'QUALIFIED'), row('KO', 'LIQUIDITY_RISK'), row('SOXS', 'REJECT')];
    expect(previewChanges(saved, preview)).toEqual({ enter: ['KO'], exit: ['SOXS'] });
  });

  it('is empty when nothing changed, and ignores rows with no symbol', () => {
    const same = [row('AAPL', 'QUALIFIED'), row(null, 'QUALIFIED')];
    expect(previewChanges(same, same)).toEqual({ enter: [], exit: [] });
  });
});
