/**
 * The Financials panel as a spec: the key-metrics strip and the five sections (Growth,
 * Profitability, Balance sheet and cash flow, Valuation, Earnings), each a list of catalogue
 * features by name with its status fields. Adding a row is one line in `SECTIONS`. The browser
 * derives nothing (ADR 0038): every figure, margin and surprise is a stored value the server
 * serves already formatted by its `info.format`.
 */
import { feature, type SiteFeature } from '@/shared/api';
import type { FactSpec } from '@/entities/feature';

/** One row: a fact plus the field whose Guide entry the row's help button opens. */
export type RowSpec = FactSpec;

export interface SectionSpec {
  id: string;
  title: string;
  /** The glossary term the section's help button opens. */
  term: string;
  /** Status and basis fields drawn as badges in the header. */
  statuses: readonly SiteFeature[];
  rows: readonly RowSpec[];
}

const f = (id: string, label: string, name: SiteFeature, signed?: boolean): RowSpec => ({
  id,
  label,
  name,
  ...(signed ? { signed } : {}),
});

/** The headline strip: the few figures that say most, in order. */
export const KEY_METRICS: readonly RowSpec[] = [
  f('revenue-growth', 'Revenue growth (YoY)', feature('feature.revenue_growth_yoy'), true),
  f('net-margin', 'Net margin', feature('feature.net_margin')),
  f('pe', 'P/E ratio', feature('feature.pe_ratio')),
  f('ps', 'P/S ratio', feature('feature.ps_ratio')),
  f('debt', 'Total debt', feature('rollup.balance_sheet@v1.total_debt')),
  f(
    'surprise',
    'Last EPS surprise',
    feature('rollup.earnings_surprise@v1.last_surprise_pct'),
    true,
  ),
];

export const SECTIONS: readonly SectionSpec[] = [
  {
    id: 'growth',
    title: 'Growth',
    term: 'financials_growth',
    statuses: [feature('rollup.financials@v2.financials_status')],
    rows: [
      f('rev-ttm', 'Revenue (TTM)', feature('rollup.financials@v2.revenue_ttm')),
      f('rev-yoy', 'Revenue growth (YoY)', feature('feature.revenue_growth_yoy'), true),
      f(
        'rev-qtr',
        'Revenue growth, quarter (YoY)',
        feature('feature.revenue_growth_qtr_yoy'),
        true,
      ),
      f('eps-yoy', 'EPS growth (YoY)', feature('feature.eps_growth_yoy'), true),
      f('eps-qtr', 'EPS growth, quarter (YoY)', feature('feature.eps_growth_qtr_yoy'), true),
    ],
  },
  {
    id: 'profitability',
    title: 'Profitability',
    term: 'financials_profitability',
    statuses: [feature('rollup.income_statement@v1.is_status')],
    rows: [
      f('income', 'Net income (TTM)', feature('rollup.financials@v2.net_income_ttm')),
      f('margin', 'Net margin', feature('feature.net_margin')),
      f('gross', 'Gross profit (TTM)', feature('rollup.income_statement@v1.gross_profit_ttm')),
      f('ebit', 'Operating income (TTM)', feature('rollup.income_statement@v1.ebit_ttm')),
      f('da', 'Depreciation and amortisation (TTM)', feature('rollup.income_statement@v1.da_ttm')),
      f(
        'interest',
        'Interest expense (TTM)',
        feature('rollup.income_statement@v1.interest_expense_ttm'),
      ),
      f('pretax', 'Pre-tax income (TTM)', feature('rollup.income_statement@v1.pretax_income_ttm')),
      f('tax', 'Income tax (TTM)', feature('rollup.income_statement@v1.income_tax_ttm')),
    ],
  },
  {
    id: 'balance',
    title: 'Balance sheet and cash flow',
    term: 'financials_balance_cash',
    statuses: [
      feature('rollup.balance_sheet@v1.bs_status'),
      feature('rollup.balance_sheet@v1.debt_basis'),
      feature('rollup.cash_flow@v1.cf_status'),
    ],
    rows: [
      f('cash', 'Cash', feature('rollup.balance_sheet@v1.cash')),
      f('sti', 'Short-term investments', feature('rollup.balance_sheet@v1.sti')),
      f('debt', 'Total debt', feature('rollup.balance_sheet@v1.total_debt')),
      f('assets', 'Total assets', feature('rollup.balance_sheet@v1.total_assets')),
      f('liabilities', 'Total liabilities', feature('rollup.balance_sheet@v1.total_liabilities')),
      f('equity', "Stockholders' equity", feature('rollup.balance_sheet@v1.stockholders_equity')),
      f('cur-assets', 'Current assets', feature('rollup.balance_sheet@v1.current_assets')),
      f('cur-liab', 'Current liabilities', feature('rollup.balance_sheet@v1.current_liabilities')),
      f('as-of', 'Balance sheet as of', feature('rollup.balance_sheet@v1.bs_as_of')),
      f('ocf', 'Operating cash flow (TTM)', feature('rollup.cash_flow@v1.ocf_ttm')),
      f('capex', 'Capital spending (TTM)', feature('rollup.cash_flow@v1.capex_ttm')),
    ],
  },
  {
    id: 'valuation',
    title: 'Valuation',
    term: 'financials_valuation',
    statuses: [],
    rows: [
      f('pe', 'P/E ratio', feature('feature.pe_ratio')),
      f('ps', 'P/S ratio', feature('feature.ps_ratio')),
      f('eps', 'Diluted EPS (TTM)', feature('rollup.financials@v2.eps_diluted_ttm')),
    ],
  },
  {
    id: 'earnings',
    title: 'Earnings: surprise and revisions',
    term: 'financials_earnings',
    statuses: [feature('rollup.earnings_surprise@v1.surprise_status')],
    rows: [
      f('reported', 'Last EPS reported', feature('rollup.earnings_surprise@v1.last_eps_reported')),
      f('forecast', 'Last EPS forecast', feature('rollup.earnings_surprise@v1.last_eps_forecast')),
      f('s-eps', 'Surprise ($)', feature('rollup.earnings_surprise@v1.last_surprise_eps'), true),
      f('s-pct', 'Surprise (%)', feature('rollup.earnings_surprise@v1.last_surprise_pct'), true),
      f(
        's-med',
        'Median surprise, last 4',
        feature('rollup.earnings_surprise@v1.surprise_median_4q'),
        true,
      ),
      f('beats', 'Beats, last 4', feature('rollup.earnings_surprise@v1.beats_4q')),
      f('reports', 'Reports, last 4', feature('rollup.earnings_surprise@v1.reports_4q')),
      f('next', 'Next EPS forecast', feature('rollup.earnings_revisions@v1.next_eps_forecast')),
      f('count', 'Estimates', feature('rollup.earnings_revisions@v1.estimate_count')),
      f(
        'rev-7',
        'Forecast revision (7d)',
        feature('rollup.earnings_revisions@v1.forecast_revision_7d'),
        true,
      ),
      f(
        'rev-30',
        'Forecast revision (30d)',
        feature('rollup.earnings_revisions@v1.forecast_revision_30d'),
        true,
      ),
      f(
        'count-30',
        'Estimate count change (30d)',
        feature('rollup.earnings_revisions@v1.estimate_count_change_30d'),
        true,
      ),
    ],
  },
];

/** Every catalogue feature the panel asks for (one request). */
export const FINANCIALS_FEATURES: readonly SiteFeature[] = [
  ...new Set([
    ...KEY_METRICS.map((r) => r.name),
    ...SECTIONS.flatMap((s) => [...s.statuses, ...s.rows.map((r) => r.name)]),
  ]),
];
