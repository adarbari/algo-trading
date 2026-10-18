import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { FINANCIALS_PARTS, KEY_METRICS, SECTIONS } from '../model/sections';
import { FinancialsPanel } from './FinancialsPanel';

const hooks = vi.hoisted(() => ({ useInstrumentFacts: vi.fn() }));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentFacts: hooks.useInstrumentFacts,
}));

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    termHelp: (id: string) => <Text>{`term ${id}`}</Text>,
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`field ${entry.id}`}</Text>,
  };
});

const info = (format: string, unit: string | null = null) => ({
  format,
  unit,
  dtype: 'float',
  nullMeaning: 'the filing does not report it',
});
const known = (name: string, v: unknown, format: string, unit: string | null = null) => ({
  name,
  value: v,
  unknown: null,
  info: info(format, unit),
});
const gap = (name: string, kind: string, guideTerm: string, kindText: string) => ({
  name,
  value: null,
  unknown: { code: 'NULL', kind, guideTerm, kindText, cause: null },
  info: info('COMPACT', 'usd'),
});

const session = { date: '2026-10-02', isLatest: true, unavailable: [] };
const stock = {
  instrumentId: 'EQ:KO',
  symbol: 'KO',
  name: 'Coca-Cola Co',
  isEtf: false,
  features: [
    known('feature.revenue_growth_yoy', 0.06, 'PERCENT', 'decimal'),
    known('feature.net_margin', 0.22, 'PERCENT', 'decimal'),
    known('feature.pe_ratio', 24.3, 'NUMBER', 'ratio'),
    known('rollup.financials@v2.revenue_ttm', 4.7e10, 'COMPACT', 'usd'),
    known('rollup.financials@v2.financials_status', 'OK', 'TEXT'),
    known('rollup.balance_sheet@v1.debt_basis', 'LT_PLUS_ST', 'TEXT'),
    gap(
      'rollup.balance_sheet@v1.total_debt',
      'LICENCE',
      'unavailable_licence',
      'needs the data licence',
    ),
    gap('feature.fcf', 'LICENCE', 'unavailable_licence', 'needs the data licence'),
    gap('rollup.cash_flow@v1.ocf_ttm', 'SYSTEM', 'unavailable_system', 'a system error'),
  ],
};

beforeEach(() => {
  hooks.useInstrumentFacts.mockReturnValue(fakeQuery({ session, instrument: stock }));
});

describe('FinancialsPanel', () => {
  it('asks for every figure in three requests and leads with the key metrics', async () => {
    const { container } = render(<FinancialsPanel symbol="KO" />);
    expect(hooks.useInstrumentFacts).toHaveBeenCalledWith('KO', FINANCIALS_PARTS[0]);
    expect(hooks.useInstrumentFacts).toHaveBeenCalledWith('KO', FINANCIALS_PARTS[1]);
    expect(hooks.useInstrumentFacts).toHaveBeenCalledWith('KO', FINANCIALS_PARTS[2]);
    const strip = screen.getByRole('region', { name: 'KO key financials' });
    expect(strip).toHaveTextContent('Operating margin');
    expect(strip).toHaveTextContent('P/E ratio');
    expect(strip).toHaveTextContent('term unavailable_licence');
    await expectNoA11yViolations(container);
  });

  it('shows the nine metrics of the strip in the owner order', () => {
    render(<FinancialsPanel symbol="KO" />);
    const strip = screen.getByRole('region', { name: 'KO key financials' });
    const text = strip.textContent;
    const at = KEY_METRICS.map((m) => text.indexOf(m.label));
    expect(KEY_METRICS).toHaveLength(9);
    expect(at.every((i) => i >= 0)).toBe(true);
    expect(at).toEqual([...at].sort((a, b) => a - b));
    expect(strip).toHaveTextContent('Forward P/E');
    expect(strip).toHaveTextContent('Forward revenue growth');
  });

  it('shows the six sections with status badges in their headers', () => {
    render(<FinancialsPanel symbol="KO" />);
    for (const title of [
      'Growth',
      'Profitability',
      'Balance sheet and cash flow',
      'Valuation',
      'Earnings: surprise and revisions',
      'Analysts: estimates and targets',
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.getByText('LT_PLUS_ST')).toBeInTheDocument();
  });

  it('shows a gated or missing value by its kind, never drops the row', () => {
    render(<FinancialsPanel symbol="KO" />);
    const balance = screen.getByLabelText('Balance sheet and cash flow');
    expect(balance).toHaveTextContent('Total debt');
    expect(balance).toHaveTextContent('needs the data licence');
    expect(balance).toHaveTextContent('term unavailable_licence');
    expect(balance).toHaveTextContent('term unavailable_system');
    expect(balance).toHaveTextContent('Operating cash flow (TTM)');
    expect(balance).toHaveTextContent('a system error');
    // a name the server did not serve at all still has its row
    expect(screen.getByLabelText('Valuation')).toHaveTextContent('P/S ratio');
    expect(screen.getByLabelText('Valuation')).toHaveTextContent('field feature.ps_ratio');
  });

  it('says a fund has no financials', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({ session, instrument: { ...stock, symbol: 'SPY', isEtf: true, features: [] } }),
    );
    render(<FinancialsPanel symbol="SPY" />);
    expect(screen.getByText('SPY is a fund and has no financials.')).toBeInTheDocument();
    expect(screen.getAllByText('term financials_panel')).toHaveLength(2);
    expect(screen.queryByRole('heading', { name: 'Growth' })).not.toBeInTheDocument();
  });

  it('shows loading and error states', () => {
    hooks.useInstrumentFacts.mockReturnValue(fakeQuery(undefined));
    const { unmount } = render(<FinancialsPanel symbol="KO" />);
    expect(screen.getByText('Loading KO…')).toBeInTheDocument();
    unmount();
    hooks.useInstrumentFacts.mockReturnValue(fakeQuery(undefined, { isError: true }));
    render(<FinancialsPanel symbol="KO" />);
    expect(screen.getByText('KO failed to load.')).toBeInTheDocument();
  });
});

const analystNames = SECTIONS.find((sec) => sec.id === 'analysts')?.rows.map((r) => r.name) ?? [];
const notCovered = (name: string) =>
  gap(name, 'NOT_COVERED', 'unavailable_not_covered', 'not covered by our analyst data');
const licence = (name: string) =>
  gap(name, 'LICENCE', 'unavailable_licence', 'needs the data licence');
const STATUSES = [
  'rollup.analyst_estimates@v1.estimates_status',
  'rollup.analyst_targets@v1.targets_status',
];
const withAnalysts = (analysts: readonly (typeof stock.features)[number][]) =>
  fakeQuery({ session, instrument: { ...stock, features: [...stock.features, ...analysts] } });

describe('the analysts section', () => {
  it('shows a covered name row by row with its status badges', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      withAnalysts([
        known('rollup.analyst_targets@v1.target_consensus', 210, 'CURRENCY', 'usd'),
        known('feature.target_upside', 0.15, 'PERCENT', 'decimal'),
        known(STATUSES[0] ?? '', 'OK', 'TEXT'),
        known(STATUSES[1] ?? '', 'STALE', 'TEXT'),
      ]),
    );
    render(<FinancialsPanel symbol="KO" />);
    const section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Price target (consensus)');
    expect(section).toHaveTextContent('Upside to target');
    // a row the server did not serve still has its place
    expect(section).toHaveTextContent('EPS estimate (FY1)');
    expect(screen.queryByText('Analyst figures')).not.toBeInTheDocument();
    expect(screen.getByText('STALE')).toBeInTheDocument();
  });

  it('says it once when the name is not covered, with the kind and its Guide term', async () => {
    hooks.useInstrumentFacts.mockReturnValue(
      withAnalysts([...analystNames, ...STATUSES].map(notCovered)),
    );
    const { container } = render(<FinancialsPanel symbol="KO" />);
    const section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Analyst figures');
    expect(section).toHaveTextContent('Not covered');
    expect(section).toHaveTextContent('term unavailable_not_covered');
    expect(section).not.toHaveTextContent('Price target (consensus)');
    expect(section).not.toHaveTextContent('Price target (consensus)');
    expect(screen.getByRole('heading', { name: 'Analysts: estimates and targets' })).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('keeps a status badge that holds a value beside the collapsed row', () => {
    hooks.useInstrumentFacts.mockReturnValue(
      withAnalysts([
        ...analystNames.map(notCovered),
        known(STATUSES[0] ?? '', 'NOT_FETCHED', 'TEXT'),
        notCovered(STATUSES[1] ?? ''),
      ]),
    );
    render(<FinancialsPanel symbol="KO" />);
    const section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Analyst figures');
    expect(screen.getByText('NOT_FETCHED')).toBeInTheDocument();
    // the targets status is itself a gap: no badge, no second Not covered word
    expect(screen.getAllByText('Not covered')).toHaveLength(1);
  });

  it('says a licence gap once too, by its own kind', () => {
    hooks.useInstrumentFacts.mockReturnValue(withAnalysts(analystNames.map(licence)));
    render(<FinancialsPanel symbol="KO" />);
    const section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Analyst figures');
    expect(section).toHaveTextContent('needs the data licence');
    expect(section).toHaveTextContent('term unavailable_licence');
    expect(section).not.toHaveTextContent('Not covered');
  });

  it('keeps every row when the gaps differ in kind or one row has a value', () => {
    const [first = '', second = '', ...others] = analystNames;
    hooks.useInstrumentFacts.mockReturnValue(
      withAnalysts([notCovered(first), licence(second), ...others.map(notCovered)]),
    );
    const { unmount } = render(<FinancialsPanel symbol="KO" />);
    let section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Price target (consensus)');
    expect(section).toHaveTextContent('term unavailable_licence');
    expect(section).toHaveTextContent('term unavailable_not_covered');
    expect(screen.queryByText('Analyst figures')).not.toBeInTheDocument();
    unmount();

    hooks.useInstrumentFacts.mockReturnValue(
      fakeQuery({
        session,
        instrument: {
          ...stock,
          features: [
            known(first, 210, 'CURRENCY', 'usd'),
            ...analystNames.slice(1).map(notCovered),
          ],
        },
      }),
    );
    render(<FinancialsPanel symbol="KO" />);
    section = screen.getByLabelText('Analysts: estimates and targets');
    expect(section).toHaveTextContent('Price target (consensus)');
    expect(screen.queryByText('Analyst figures')).not.toBeInTheDocument();
  });
});
