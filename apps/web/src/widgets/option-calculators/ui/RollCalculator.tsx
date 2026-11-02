/**
 * Roll a put (plan V11, screen OptRoll): the trader types the put they sold (strike, expiry and,
 * to get a breakeven, the price they sold it at) and sees what buying it back costs tonight and
 * the rolls to a later expiry that pay a credit. Basics shows the four figures to decide on; More
 * adds the credit per extra day and our delta, and two choices that ask the server again (one strike
 * per expiry at the same delta; rolls that cost money). Every figure is the server's, priced at the
 * middle of tonight's end-of-day chain. Nothing typed is saved: it lives in this component only.
 */
import {
  Button,
  Checkbox,
  DataTable,
  Field,
  Grid,
  NumberInput,
  Panel,
  SegmentedControl,
  Select,
  Stack,
  Text,
  type SelectOption,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { termHelp } from '@/features/guide-help';
import {
  rollBody,
  rollSentence,
  shownRolls,
  useRollPreview,
  VISIBLE_ROLLS,
  type RollForm,
} from '@/features/option-calculators';
import { columnLabel, columnSub, gridOf, useOptionGrid } from '@/entities/option-grid';

import { rollColumns } from '../model/columns';
import { CalculatorFooter } from './CalculatorFooter';
import { failureMessage, GapLine } from './ErrorLine';

export interface RollCalculatorProps {
  symbol: string;
  /** Opens the Calls on shares tab ("Rather be assigned?"). */
  onOpenCalls: () => void;
}

type Detail = 'basics' | 'more';

export function RollCalculator({ symbol, onOpenCalls }: RollCalculatorProps) {
  const grid = gridOf(useOptionGrid(symbol).data);
  const expiries: SelectOption[] = useMemo(
    () =>
      (grid?.columns ?? []).flatMap((c) =>
        c.expiry === null
          ? []
          : [{ value: c.expiry, label: `${columnLabel(c)} · ${columnSub(c) ?? ''}` }],
      ),
    [grid],
  );
  const [form, setForm] = useState<RollForm>({ strike: null, expiry: '', soldAt: null });
  const [detail, setDetail] = useState<Detail>('basics');
  const [sameDelta, setSameDelta] = useState(false);
  const [includeDebits, setIncludeDebits] = useState(false);
  const [sent, setSent] = useState<RollForm | null>(null);
  const [all, setAll] = useState(false);
  const mutation = useRollPreview();

  const [asked, setAsked] = useState(false);
  const options = { includeDebits, sameDelta };
  const send = (what: RollForm, next: typeof options) => {
    setAsked(true);
    const body = rollBody(symbol, what, next);
    if (!body) return;
    setSent(what);
    setAll(false);
    mutation.mutate(body);
  };

  const result = mutation.data;
  const preview = result?.preview ?? null;
  const rolls = preview?.rolls ?? [];
  const state = mutation.isError
    ? 'error'
    : mutation.isPending
      ? 'loading'
      : result?.gap
        ? 'empty'
        : 'ready';

  return (
    <Grid columns="main-aside" gap={4} collapse="md" align="start">
      <Stack gap={4}>
        <Panel
          title="Your contract"
          actions={termHelp('roll_your_contract')}
          footer="Nothing you type is saved. Uses tonight's end-of-day chain."
        >
          <Stack gap={3}>
            <Grid columns={3} gap={3} collapse="md" align="start">
              <Field
                label="Strike"
                error={
                  asked && (form.strike === null || form.strike <= 0)
                    ? 'Enter the strike'
                    : undefined
                }
              >
                <NumberInput
                  prefix="$"
                  step={0.5}
                  precision={2}
                  min={0}
                  value={form.strike}
                  onValueChange={(strike) => {
                    setForm({ ...form, strike });
                  }}
                />
              </Field>
              <Field
                label="Expiry"
                error={asked && form.expiry === '' ? 'Pick your put’s expiry' : undefined}
              >
                <Select
                  options={expiries}
                  placeholder="Choose an expiry"
                  value={form.expiry}
                  onValueChange={(expiry) => {
                    setForm({ ...form, expiry });
                  }}
                />
              </Field>
              <Stack direction="row" gap={1} align="end">
                <Field label="Sold at (optional, for your breakeven)">
                  <NumberInput
                    prefix="$"
                    step={0.05}
                    precision={2}
                    min={0}
                    value={form.soldAt}
                    onValueChange={(soldAt) => {
                      setForm({ ...form, soldAt });
                    }}
                  />
                </Field>
                {termHelp('roll_sold_at')}
              </Stack>
            </Grid>
            <Stack direction="row" gap={2} align="center">
              <Button
                variant="primary"
                loading={mutation.isPending}
                onClick={() => {
                  send(form, options);
                }}
              >
                Show rolls
              </Button>
            </Stack>
          </Stack>
        </Panel>

        {preview && (
          <Stack direction="row" gap={1} align="center">
            <Text>{rollSentence(symbol, preview)}</Text>
            {termHelp('roll_buy_back')}
          </Stack>
        )}

        {(sent || mutation.isPending) && (
          <Panel
            title="Rolls for a credit"
            actions={
              <Stack direction="row" gap={2} wrap align="center">
                {termHelp('roll_rolls_for_credit')}
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
            loadingLabel={`Loading ${symbol} rolls…`}
            errorMessage={failureMessage(symbol, mutation.error)}
            onRetry={() => {
              if (sent) send(sent, options);
            }}
            emptyMessage={result?.gap ? <GapLine gap={result.gap} /> : null}
          >
            <Stack gap={3}>
              {detail === 'more' && (
                <Stack direction="row" gap={4} wrap align="center">
                  <Stack direction="row" gap={1} align="center">
                    <Checkbox
                      label="Roll to the same delta"
                      checked={sameDelta}
                      onCheckedChange={(checked) => {
                        setSameDelta(checked);
                        if (sent) send(sent, { includeDebits, sameDelta: checked });
                      }}
                    />
                    {termHelp('roll_same_delta')}
                  </Stack>
                  <Stack direction="row" gap={1} align="center">
                    <Checkbox
                      label="Include rolls that cost money"
                      checked={includeDebits}
                      onCheckedChange={(checked) => {
                        setIncludeDebits(checked);
                        if (sent) send(sent, { includeDebits: checked, sameDelta });
                      }}
                    />
                    {termHelp('roll_include_debits')}
                  </Stack>
                </Stack>
              )}
              <DataTable
                label={`${symbol} rolls for a credit`}
                columns={rollColumns(detail === 'more')}
                rows={shownRolls(rolls, all)}
                getRowId={(r) => `${r.expiry}-${String(r.strike)}`}
                activateOnClick={false}
                visibleRows="all"
                emptyMessage="No roll pays a credit tonight."
              />
              {!all && rolls.length > VISIBLE_ROLLS && (
                <Stack direction="row" gap={2}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setAll(true);
                    }}
                  >
                    {`See all ${String(rolls.length)}`}
                  </Button>
                </Stack>
              )}
            </Stack>
          </Panel>
        )}
        <CalculatorFooter />
      </Stack>

      <Panel title="Rather be assigned?" actions={termHelp('roll_rather_assigned')}>
        <Stack gap={3}>
          <Text size="sm">Sell a call on shares you own instead.</Text>
          <Stack direction="row" gap={2}>
            <Button onClick={onOpenCalls}>Calls on shares</Button>
          </Stack>
        </Stack>
      </Panel>
    </Grid>
  );
}
