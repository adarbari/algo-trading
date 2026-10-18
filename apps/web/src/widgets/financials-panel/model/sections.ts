/**
 * The Financials panel as a spec: the key-metrics strip and the six sections (Growth,
 * Profitability, Balance sheet and cash flow, Valuation, Earnings, Analysts), each a list of catalogue
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
  /**
   * The label of the one row that replaces the section's rows when every one of them is a gap
   * of the same kind (an uncovered name has no analyst figure at all). The kind is the
   * server's; the browser only chooses to say it once.
   */
  collapseGaps?: string;
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

/**
 * The headline strip, in the owner's order: P/E, forward P/E, revenue growth, forward revenue,
 * EPS growth, operating margin, debt to equity, free cash flow, last EPS surprise. Forward
 * revenue reads as its growth over the last twelve months (a rate scans at a glance and sits
 * beside the reported growth; a bare amount has no base to read against); the amounts are in
 * the Analysts section.
 */
export const KEY_METRICS: readonly RowSpec[] = [
  f('pe', 'P/E ratio', feature('feature.pe_ratio')),
  f('forward-pe', 'Forward P/E', feature('feature.forward_pe')),
  f('revenue-growth', 'Revenue growth (YoY)', feature('feature.revenue_growth_yoy'), true),
  f('forward-revenue', 'Forward revenue growth', feature('feature.forward_revenue_growth'), true),
  f('eps-growth', 'EPS growth (YoY)', feature('feature.eps_growth_yoy'), true),
  f('op-margin', 'Operating margin', feature('feature.operating_margin')),
  f('d-e', 'Debt to equity', feature('feature.debt_to_equity')),
  f('fcf', 'Free cash flow', feature('feature.fcf')),
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
    statuses: [
      feature('rollup.financials@v2.financials_status'),
      feature('rollup.growth_history@v1.gh_status'),
    ],
    rows: [
      f('rev-ttm', 'Revenue (TTM)', feature('rollup.financials@v2.revenue_ttm')),
      f(
        'rev-qtr',
        'Revenue growth, quarter (YoY)',
        feature('feature.revenue_growth_qtr_yoy'),
        true,
      ),
      f('eps-qtr', 'EPS growth, quarter (YoY)', feature('feature.eps_growth_qtr_yoy'), true),
      f('rev-cagr-3', 'Revenue CAGR (3y)', feature('feature.revenue_cagr_3y'), true),
      f('rev-cagr-5', 'Revenue CAGR (5y)', feature('feature.revenue_cagr_5y'), true),
      f('eps-cagr-3', 'EPS CAGR (3y)', feature('feature.eps_cagr_3y'), true),
      f('eps-cagr-5', 'EPS CAGR (5y)', feature('feature.eps_cagr_5y'), true),
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
      f('gross-margin', 'Gross margin', feature('feature.gross_margin')),
      f('ebitda', 'EBITDA', feature('feature.ebitda')),
      f('roe', 'Return on equity', feature('feature.roe')),
      f('roa', 'Return on assets', feature('feature.roa')),
      f('roic', 'Return on invested capital', feature('feature.roic')),
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
      feature('rollup.cash_flow@v1.cf_status'),
    ],
    rows: [
      f('cash', 'Cash', feature('rollup.balance_sheet@v1.cash')),
      f('sti', 'Short-term investments', feature('rollup.balance_sheet@v1.sti')),
      f('debt', 'Total debt', feature('rollup.balance_sheet@v1.total_debt')),
      f('net-debt', 'Net debt', feature('feature.net_debt')),
      f('debt-basis', 'Debt basis', feature('rollup.balance_sheet@v1.debt_basis')),
      f('assets', 'Total assets', feature('rollup.balance_sheet@v1.total_assets')),
      f('liabilities', 'Total liabilities', feature('rollup.balance_sheet@v1.total_liabilities')),
      f('equity', "Stockholders' equity", feature('rollup.balance_sheet@v1.stockholders_equity')),
      f('cur-assets', 'Current assets', feature('rollup.balance_sheet@v1.current_assets')),
      f('cur-liab', 'Current liabilities', feature('rollup.balance_sheet@v1.current_liabilities')),
      f('as-of', 'Balance sheet as of', feature('rollup.balance_sheet@v1.bs_as_of')),
      f('ocf', 'Operating cash flow (TTM)', feature('rollup.cash_flow@v1.ocf_ttm')),
      f('fcf-yield', 'Free cash flow yield', feature('feature.fcf_yield')),
      f('capex', 'Capital spending (TTM)', feature('rollup.cash_flow@v1.capex_ttm')),
    ],
  },
  {
    id: 'valuation',
    title: 'Valuation',
    term: 'financials_valuation',
    statuses: [],
    rows: [
      f('ps', 'P/S ratio', feature('feature.ps_ratio')),
      f('eps', 'Diluted EPS (TTM)', feature('rollup.financials@v2.eps_diluted_ttm')),
      f('pb', 'P/B ratio', feature('feature.pb_ratio')),
      f('ev', 'Enterprise value', feature('feature.enterprise_value')),
      f('ev-ebitda', 'EV / EBITDA', feature('feature.ev_ebitda')),
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
  {
    id: 'analysts',
    title: 'Analysts: estimates and targets',
    term: 'financials_analyst',
    collapseGaps: 'Analyst figures',
    statuses: [
      feature('rollup.analyst_estimates@v1.estimates_status'),
      feature('rollup.analyst_targets@v1.targets_status'),
    ],
    // Not in the catalogue yet (PR #625): rollup.analyst_ratings@v1 rating_strong_buy ..
    // rating_strong_sell, rating_count, rating_score, rating_month, rating_score_change_90d,
    // ratings_status; rollup.analyst_revisions@v1 eps_fy1_revision_30d / 60d / 90d,
    // revenue_fy1_revision_30d / 90d, eps_fy1_analysts_change_90d, revisions_status. Add the
    // rows (and the two statuses) here when they exist; forward P/E and forward revenue growth
    // are in the strip and not repeated.
    rows: [
      f(
        'target',
        'Price target (consensus)',
        feature('rollup.analyst_targets@v1.target_consensus'),
      ),
      f('upside', 'Upside to target', feature('feature.target_upside'), true),
      f('target-high', 'Price target (high)', feature('rollup.analyst_targets@v1.target_high')),
      f('target-low', 'Price target (low)', feature('rollup.analyst_targets@v1.target_low')),
      f('eps-fy1', 'EPS estimate (FY1)', feature('rollup.analyst_estimates@v1.eps_fy1')),
      f('eps-fy2', 'EPS estimate (FY2)', feature('rollup.analyst_estimates@v1.eps_fy2')),
      f('fy1-end', 'FY1 ends', feature('rollup.analyst_estimates@v1.fy1_period_end')),
      f('fwd-eps-growth', 'Forward EPS growth (FY1)', feature('feature.forward_eps_growth'), true),
      f('fwd-pe-fy2', 'Forward P/E (FY2)', feature('feature.forward_pe_fy2')),
      f('rev-fy1', 'Revenue estimate (FY1)', feature('rollup.analyst_estimates@v1.revenue_fy1')),
      f('rev-fy2', 'Revenue estimate (FY2)', feature('rollup.analyst_estimates@v1.revenue_fy2')),
      f(
        'eps-analysts',
        'Analysts behind EPS (FY1)',
        feature('rollup.analyst_estimates@v1.eps_fy1_analysts'),
      ),
      f(
        'rev-analysts',
        'Analysts behind revenue (FY1)',
        feature('rollup.analyst_estimates@v1.revenue_fy1_analysts'),
      ),
    ],
  },
];

const namesOf = (sections: readonly SectionSpec[], extra: readonly RowSpec[] = []) => [
  ...new Set([
    ...extra.map((r) => r.name),
    ...sections.flatMap((s) => [...s.statuses, ...s.rows.map((r) => r.name)]),
  ]),
];

const BALANCE = SECTIONS.filter((s) => s.id === 'balance');
const ANALYSTS = SECTIONS.filter((s) => s.id === 'analysts');

/**
 * The catalogue features the panel asks for, in three requests (the API caps `features(names)`
 * at `NAMES_PER_REQUEST`): the strip and the sections that are neither the balance sheet nor
 * the analysts, then the balance sheet and cash flow, then the analysts. A test keeps each part
 * under the cap.
 */
export const FINANCIALS_PARTS: readonly (readonly SiteFeature[])[] = [
  namesOf(
    SECTIONS.filter((s) => s.id !== 'balance' && s.id !== 'analysts'),
    KEY_METRICS,
  ),
  namesOf(BALANCE),
  namesOf(ANALYSTS),
];
