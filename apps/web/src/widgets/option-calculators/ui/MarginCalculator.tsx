/**
 * Buying power (plan V11, screen OptMargin): the trader types a contract and how many, and sees
 * what it ties up: cash-secured or in a margin account (the exchange minimum, Reg-T, never a named
 * broker's rule), the premium collected over it, how big the order is against today's trading, and
 * for a put what it would cost if the stock fell like its worst stored episode. Every figure is the
 * server's. Nothing typed is saved: it lives in this component only.
 */
import {
  Button,
  Field,
  Grid,
  Heading,
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
  heldFigures,
  marginBody,
  premiumLine,
  premiumTotal,
  sizeLines,
  stressSentence,
  useMarginPreview,
  type Account,
  type MarginForm,
} from '@/features/option-calculators';
import { columnLabel, columnSub, gridOf, useOptionGrid } from '@/entities/option-grid';

import { CalculatorFooter } from './CalculatorFooter';
import { failureMessage, GapLine } from './ErrorLine';

export interface MarginCalculatorProps {
  symbol: string;
}

type Right = MarginForm['right'];

export function MarginCalculator({ symbol }: MarginCalculatorProps) {
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
  const [form, setForm] = useState<MarginForm>({
    right: 'put',
    strike: null,
    expiry: '',
    contracts: null,
  });
  const [account, setAccount] = useState<Account>('margin');
  const [sent, setSent] = useState(false);
  const [asked, setAsked] = useState(false);
  const mutation = useMarginPreview();
  const body = marginBody(symbol, form);
  // An edit clears the last result: figures for another contract never stand under this one.
  const edit = (next: MarginForm) => {
    setForm(next);
    setSent(false);
    mutation.reset();
  };

  const result = mutation.data;
  const preview = result?.preview ?? null;
  const state = mutation.isError
    ? 'error'
    : mutation.isPending
      ? 'loading'
      : result?.gap
        ? 'empty'
        : 'ready';
  const figures = preview ? heldFigures(preview, account) : null;
  const size = preview ? sizeLines(preview) : [];
  const stress = preview ? stressSentence(symbol, preview) : null;

  return (
    <Stack gap={4}>
      <Panel
        title="Your contract"
        actions={termHelp('margin_buying_power')}
        footer={
          <Text size="sm">Nothing you enter is saved.</Text>
        }
      >
        <Stack gap={3}>
          <Grid columns={4} gap={3} collapse="md" align="start">
            <Field label="Right">
              <SegmentedControl<Right>
                aria-label="Right"
                options={[
                  { value: 'put', label: 'Put' },
                  { value: 'call', label: 'Call' },
                ]}
                value={form.right}
                onValueChange={(right) => {
                  edit({ ...form, right });
                }}
              />
            </Field>
            <Field
              label="Strike"
              error={
                asked && (form.strike === null || form.strike <= 0) ? 'Enter the strike' : undefined
              }
            >
              <NumberInput
                prefix="$"
                step={0.5}
                precision={2}
                min={0}
                value={form.strike}
                onValueChange={(strike) => {
                  edit({ ...form, strike });
                }}
              />
            </Field>
            <Field
              label="Expiry"
              error={asked && form.expiry === '' ? 'Pick the contract’s expiry' : undefined}
            >
              <Select
                options={expiries}
                placeholder="Choose an expiry"
                value={form.expiry}
                onValueChange={(expiry) => {
                  edit({ ...form, expiry });
                }}
              />
            </Field>
            <Stack direction="row" gap={1} align="end">
              <Field
                label="Contracts"
                error={
                  asked &&
                  (form.contracts === null ||
                    !Number.isInteger(form.contracts) ||
                    form.contracts <= 0)
                    ? 'Enter whole contracts'
                    : undefined
                }
              >
                <NumberInput
                  min={0}
                  step={1}
                  value={form.contracts}
                  onValueChange={(contracts) => {
                    edit({ ...form, contracts });
                  }}
                />
              </Field>
              {termHelp('margin_contracts')}
            </Stack>
          </Grid>
          <Stack direction="row" gap={2} align="center" wrap>
            <Button
              variant="primary"
              loading={mutation.isPending}
              onClick={() => {
                setAsked(true);
                if (!body) return;
                setSent(true);
                mutation.mutate(body);
              }}
            >
              Calculate
            </Button>
            <Stack direction="row" gap={1} align="center">
              <Text size="sm" tone="muted">
                Exchange minimum (Reg-T)
              </Text>
              {termHelp('margin_reg_t')}
            </Stack>
          </Stack>
        </Stack>
      </Panel>

      {(sent || mutation.isPending) && (
        <Panel
          title="What it ties up"
          actions={
            <Stack direction="row" gap={2} wrap align="center">
              {termHelp('margin_buying_power')}
              <SegmentedControl<Account>
                aria-label="Account"
                size="sm"
                options={[
                  { value: 'cash', label: 'Cash-secured' },
                  { value: 'margin', label: 'Margin account' },
                ]}
                value={account}
                onValueChange={setAccount}
              />
            </Stack>
          }
          state={state}
          loadingLabel={`Loading ${symbol} buying power…`}
          errorMessage={failureMessage(symbol, mutation.error)}
          onRetry={() => {
            if (body) mutation.mutate(body);
          }}
          emptyMessage={result?.gap ? <GapLine gap={result.gap} /> : null}
        >
          {preview && figures && (
            <Stack gap={4}>
              <Grid columns={2} gap={4} collapse="md" align="start">
                <Stack gap={1}>
                  <Stack direction="row" gap={1} align="center">
                    <Text size="sm" tone="muted">
                      {figures.headline.label}
                    </Text>
                    {termHelp('margin_held')}
                  </Stack>
                  <Heading level={3}>{figures.headline.value}</Heading>
                  <Text size="sm" tone="muted">
                    {`${figures.other.label} ${figures.other.value}`}
                  </Text>
                </Stack>
                <Stack gap={1}>
                  <Stack direction="row" gap={1} align="center">
                    <Text size="sm" tone="muted">
                      Premium collected
                    </Text>
                    {termHelp('margin_premium_collected')}
                  </Stack>
                  <Heading level={3}>{premiumTotal(preview)}</Heading>
                  <Text size="sm" tone="muted">
                    {premiumLine(preview, account)}
                  </Text>
                </Stack>
              </Grid>
              {size.length > 0 && (
                <Stack gap={1}>
                  <Stack direction="row" gap={1} align="center">
                    <Text weight="medium">Size against trading</Text>
                    {termHelp('margin_size')}
                  </Stack>
                  {size.map((line) => (
                    <Text key={line}>{line}</Text>
                  ))}
                </Stack>
              )}
              {(stress ?? preview.stress_unknown) && (
                <Stack gap={1}>
                  <Stack direction="row" gap={1} align="center">
                    <Text weight="medium">If it fell like its worst stored episode</Text>
                    {termHelp('margin_stress')}
                  </Stack>
                  {stress ? <Text>{stress}</Text> : null}
                  {!stress && preview.stress_unknown ? (
                    <GapLine gap={preview.stress_unknown} />
                  ) : null}
                </Stack>
              )}
            </Stack>
          )}
        </Panel>
      )}
      <CalculatorFooter />
    </Stack>
  );
}
