import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { FINANCIALS_FEATURES } from '../model/sections';
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
    gap('rollup.cash_flow@v1.ocf_ttm', 'SYSTEM', 'unavailable_system', 'a system error'),
  ],
};

beforeEach(() => {
  hooks.useInstrumentFacts.mockReturnValue(fakeQuery({ session, instrument: stock }));
});

describe('FinancialsPanel', () => {
  it('asks for every figure in one request and leads with the key metrics', async () => {
    const { container } = render(<FinancialsPanel symbol="KO" />);
    expect(hooks.useInstrumentFacts).toHaveBeenCalledWith('KO', FINANCIALS_FEATURES);
    expect(hooks.useInstrumentFacts).toHaveBeenCalledTimes(1);
    const strip = screen.getByRole('region', { name: 'KO key financials' });
    expect(strip).toHaveTextContent('Net margin');
    expect(strip).toHaveTextContent('P/E ratio24.30');
    await expectNoA11yViolations(container);
  });

  it('shows the five sections with status badges in their headers', () => {
    render(<FinancialsPanel symbol="KO" />);
    for (const title of [
      'Growth',
      'Profitability',
      'Balance sheet and cash flow',
      'Valuation',
      'Earnings: surprise and revisions',
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
