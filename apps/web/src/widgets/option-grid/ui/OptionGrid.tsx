/**
 * Option grid: the focused ticker's sold-option yield a year, puts or calls, one row per delta
 * band and one column per expiry (GraphQL `Instrument.optionGrid`; ADR 0083 amendment). A cell
 * shows its yield tinted by size and the strike (More adds our mid and open interest); a cell
 * with no figure shows why, never a blank or zero; an expiry that holds the company's report
 * flags its cells. Picking a cell shows its figures. Derived figures only: no vendor bid, ask,
 * last or size reaches this screen.
 */
import {
  EmptyState,
  formatValue,
  HeatGrid,
  Panel,
  SegmentedControl,
  Stack,
  Surface,
  Text,
  type HeatGridCell,
  type HeatGridPosition,
  type HeatGridRow,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  gridOf,
  gridUnknown,
  gridView,
  useOptionGrid,
  type DisplayCell,
  type DisplayColumn,
  type GridSide,
} from '@/entities/option-grid';
import { termHelp } from '@/features/guide-help';

import { CellDetail } from './CellDetail';

export interface OptionGridProps {
  symbol: string;
}

type Detail = 'basics' | 'more';

function heatCell(cell: DisplayCell, column: DisplayColumn, detail: Detail): HeatGridCell {
  if (cell.kind === 'unknown') {
    // A cell without a level shows its text only, so the public kind is the text.
    return { status: 'not-collected', text: cell.unknown.kindText };
  }
  const { figures } = cell;
  const strike = formatValue(figures.strike, { kind: 'number', digits: 2 }).text;
  const more =
    detail === 'more'
      ? ` · ${formatValue(figures.mid, { kind: 'currency' }).text} · ${formatValue(figures.openInterest, { kind: 'number' }).text}`
      : '';
  return {
    status: 'complete',
    text: cell.text,
    level: cell.level,
    sub: `${strike}${more}`,
    ...(column.reportInside === true ? { flag: 'report' } : {}),
  };
}

export function OptionGrid({ symbol }: OptionGridProps) {
  const query = useOptionGrid(symbol);
  const [side, setSide] = useState<GridSide>('puts');
  const [detail, setDetail] = useState<Detail>('basics');
  const [selected, setSelected] = useState<HeatGridPosition | null>(null);
  const grid = gridOf(query.data);
  const why = gridUnknown(query.data);
  const view = useMemo(() => (grid ? gridView(grid, side) : null), [grid, side]);

  const rows: HeatGridRow[] = useMemo(
    () =>
      (view?.rows ?? []).map((row) => ({
        id: row.id,
        label: row.label,
        cells: Object.fromEntries(
          view?.columns.flatMap((column) => {
            const cell = row.cells[column.id];
            return cell ? [[column.id, heatCell(cell, column, detail)]] : [];
          }) ?? [],
        ),
      })),
    [view, detail],
  );
  const chosen = useMemo(() => {
    if (!selected) return null;
    const cell = view?.rows.find((r) => r.id === selected.row)?.cells[selected.column];
    return cell?.kind === 'cell' ? cell.figures : null;
  }, [selected, view]);

  const empty = query.data === null || query.data === undefined ? false : why !== null;
  const state = query.isError ? 'error' : query.isPending ? 'loading' : empty ? 'empty' : 'ready';
  return (
    <Panel
      title={`${symbol} · option grid`}
      actions={
        <Stack direction="row" gap={2} wrap align="center">
          {termHelp('option_grid')}
          <SegmentedControl<GridSide>
            aria-label="Puts or calls"
            size="sm"
            options={[
              { value: 'puts', label: 'Puts' },
              { value: 'calls', label: 'Calls' },
            ]}
            value={side}
            onValueChange={(next) => {
              setSide(next);
              setSelected(null);
            }}
          />
          <SegmentedControl<Detail>
            aria-label="Detail"
            size="sm"
            options={[
              { value: 'basics', label: 'Basics' },
              { value: 'more', label: 'More' },
            ]}
            value={detail}
            onValueChange={setDetail}
          />
        </Stack>
      }
      state={state}
      loadingLabel={`Loading the ${symbol} option grid…`}
      errorMessage={`${symbol} option grid failed to load.`}
      onRetry={() => void query.refetch()}
      emptyMessage={
        why ? (
          <Stack direction="row" gap={1} align="center">
            <Text>{why.kindText}</Text>
            {termHelp(why.guideTerm)}
          </Stack>
        ) : null
      }
    >
      {query.data === null ? (
        <EmptyState
          bordered
          title={`${symbol} is not in the reference snapshot for the session.`}
        />
      ) : (
        <Stack gap={3}>
          <Stack direction="row" gap={3} wrap align="center">
            <Stack direction="row" gap={1} align="center">
              <Text size="xs" tone="muted">
                Delta
              </Text>
              {termHelp('delta_band')}
            </Stack>
            <Stack direction="row" gap={1} align="center">
              <Text size="xs" tone="muted">
                Report inside
              </Text>
              {termHelp('report_inside_expiry')}
            </Stack>
          </Stack>
          <HeatGrid
            label={`${symbol} ${side} yield a year by delta and expiry`}
            rowHeader="Delta"
            rows={rows}
            columns={(view?.columns ?? []).map((c) => ({
              id: c.id,
              label: c.label,
              ...(c.sub === undefined ? {} : { sub: c.sub }),
            }))}
            selected={selected}
            onSelect={setSelected}
            legend={false}
          />
          <Surface>
            {chosen ? (
              <CellDetail figures={chosen} />
            ) : (
              <Text size="sm" tone="muted">
                Pick a cell to see its figures.
              </Text>
            )}
          </Surface>
        </Stack>
      )}
    </Panel>
  );
}
