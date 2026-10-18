import { describe, expect, it } from 'vitest';

import { NAMES_PER_REQUEST } from '@/entities/instrument';

import { FINANCIALS_PARTS, KEY_METRICS, SECTIONS } from './sections';

describe('the key metrics strip', () => {
  it('has the owner nine, in the owner order', () => {
    expect(KEY_METRICS.map((m) => m.name)).toEqual([
      'feature.pe_ratio',
      'feature.forward_pe',
      'feature.revenue_growth_yoy',
      'feature.forward_revenue_growth',
      'feature.eps_growth_yoy',
      'feature.operating_margin',
      'feature.debt_to_equity',
      'feature.fcf',
      'rollup.earnings_surprise@v1.last_surprise_pct',
    ]);
  });

  it('shows the growths signed', () => {
    const signed = KEY_METRICS.filter((m) => m.signed).map((m) => m.id);
    expect(signed).toEqual(['revenue-growth', 'forward-revenue', 'eps-growth', 'surprise']);
  });
});

describe('the analysts section', () => {
  const analysts = SECTIONS.find((s) => s.id === 'analysts');

  it('follows the earnings section and says it once when every row is the same gap', () => {
    expect(SECTIONS.map((s) => s.id).slice(-2)).toEqual(['earnings', 'analysts']);
    expect(analysts?.term).toBe('financials_analyst');
    expect(analysts?.collapseGaps).toBeTruthy();
  });

  it('reads the targets, the estimates and the forward formulas, with both statuses', () => {
    expect(analysts?.rows.map((r) => r.name)).toEqual([
      'rollup.analyst_targets@v1.target_consensus',
      'feature.target_upside',
      'rollup.analyst_targets@v1.target_high',
      'rollup.analyst_targets@v1.target_low',
      'rollup.analyst_estimates@v1.eps_fy1',
      'rollup.analyst_estimates@v1.eps_fy2',
      'rollup.analyst_estimates@v1.fy1_period_end',
      'feature.forward_eps_growth',
      'feature.forward_pe_fy2',
      'rollup.analyst_estimates@v1.revenue_fy1',
      'rollup.analyst_estimates@v1.revenue_fy2',
      'rollup.analyst_estimates@v1.eps_fy1_analysts',
      'rollup.analyst_estimates@v1.revenue_fy1_analysts',
    ]);
    expect(analysts?.statuses).toEqual([
      'rollup.analyst_estimates@v1.estimates_status',
      'rollup.analyst_targets@v1.targets_status',
    ]);
  });

  it('repeats no strip metric', () => {
    const strip = new Set(KEY_METRICS.map((m) => m.name));
    for (const row of analysts?.rows ?? []) expect(strip.has(row.name)).toBe(false);
  });
});

describe('the names the panel sends', () => {
  it('stay within the API cap per request and cover every strip and section name', () => {
    expect(FINANCIALS_PARTS).toHaveLength(3);
    for (const part of FINANCIALS_PARTS) expect(part.length).toBeLessThanOrEqual(NAMES_PER_REQUEST);
    const sent = new Set(FINANCIALS_PARTS.flat());
    for (const m of KEY_METRICS) expect(sent.has(m.name)).toBe(true);
    for (const section of SECTIONS) {
      for (const name of [...section.statuses, ...section.rows.map((r) => r.name)]) {
        expect(sent.has(name)).toBe(true);
      }
    }
  });

  it('send the analyst names in their own request and no name twice', () => {
    const [, , analystPart = []] = FINANCIALS_PARTS;
    expect(analystPart).toContain('rollup.analyst_targets@v1.target_consensus');
    const all = FINANCIALS_PARTS.flat();
    expect(new Set(all).size).toBe(all.length);
  });
});
