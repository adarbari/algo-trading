/**
 * Calls on shares (plan V11, screen OptCalls): the trader types the shares they hold and the price
 * they count them at (after premiums already collected) and sees the calls they could sell
 * tonight, with the premium, the premium over their price, the return if called away and what to
 * watch for (a report inside the expiry, an ex-dividend date before it, early exercise). A call
 * struck below their price shows muted, with a label. Every figure is the server's, priced at the
 * middle of tonight's end-of-day chain. Nothing typed is saved: it lives in this component only.
 */
import { Button, DataTable, Field, Grid, NumberInput, Panel, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import { termHelp } from '@/features/guide-help';
import {
  callsBody,
  type CallsBody,
  closedSentence,
  contractsText,
  dividendLine,
  useCallsPreview,
  type CallsForm,
} from '@/features/option-calculators';

import { callColumns } from '../model/columns';
import { CalculatorFooter } from './CalculatorFooter';
import { failureMessage, GapLine } from './ErrorLine';

export interface CallsCalculatorProps {
  symbol: string;
}

export function CallsCalculator({ symbol }: CallsCalculatorProps) {
  const [form, setForm] = useState<CallsForm>({ shares: null, price: null });
  // The body last sent: Retry resends it, whatever the form holds now.
  const [sent, setSent] = useState<CallsBody | null>(null);
  const [asked, setAsked] = useState(false);
  const mutation = useCallsPreview();
  const body = callsBody(symbol, form);

  const result = mutation.data;
  const preview = result?.preview ?? null;
  const state = mutation.isError
    ? 'error'
    : mutation.isPending
      ? 'loading'
      : result?.gap
        ? 'empty'
        : 'ready';
  const dividend = preview?.dividend ? dividendLine(preview.dividend) : null;

  return (
    <Stack gap={4}>
      <Panel
        title="Your shares"
        actions={termHelp('calls_shares_held')}
        footer="Nothing you type is saved."
      >
        <Stack gap={3}>
          <Grid columns={2} gap={3} collapse="md" align="start">
            <Stack direction="row" gap={1} align="end">
              <Field
                label="Shares you hold"
                error={
                  asked &&
                  (form.shares === null || !Number.isInteger(form.shares) || form.shares <= 0)
                    ? 'Enter whole shares'
                    : undefined
                }
              >
                <NumberInput
                  min={0}
                  step={100}
                  value={form.shares}
                  onValueChange={(shares) => {
                    setForm({ ...form, shares });
                  }}
                />
              </Field>
              {termHelp('calls_shares_held')}
            </Stack>
            <Stack direction="row" gap={1} align="end">
              <Field
                label="Your price (after premiums collected)"
                error={
                  asked && (form.price === null || form.price <= 0) ? 'Enter your price' : undefined
                }
              >
                <NumberInput
                  prefix="$"
                  step={0.5}
                  precision={2}
                  min={0}
                  value={form.price}
                  onValueChange={(price) => {
                    setForm({ ...form, price });
                  }}
                />
              </Field>
              {termHelp('calls_your_price')}
            </Stack>
          </Grid>
          <Stack direction="row" gap={2} align="center">
            <Button
              variant="primary"
              loading={mutation.isPending}
              onClick={() => {
                setAsked(true);
                if (!body) return;
                setSent(body);
                mutation.mutate(body);
              }}
            >
              Show calls
            </Button>
          </Stack>
        </Stack>
      </Panel>

      {preview && (
        <Stack direction="row" gap={1} align="center">
          <Text>{closedSentence(symbol, preview)}</Text>
          {termHelp('calls_closed_at')}
        </Stack>
      )}

      {(sent || mutation.isPending) && (
        <>
          <Panel
            title="Calls you could sell on these shares"
            description={preview ? contractsText(preview.contracts) : undefined}
            actions={termHelp('calls_could_sell')}
            state={state}
            loadingLabel={`Loading ${symbol} calls…`}
            errorMessage={failureMessage(symbol, mutation.error)}
            onRetry={() => {
              if (sent) mutation.mutate(sent);
            }}
            emptyMessage={result?.gap ? <GapLine gap={result.gap} /> : null}
          >
            <DataTable
              label={`${symbol} calls you could sell`}
              columns={callColumns}
              rows={preview?.rows ?? []}
              getRowId={(r) => `${r.expiry}-${String(r.strike)}`}
              activateOnClick={false}
              visibleRows="all"
              emptyMessage="No call has a two-sided quote tonight."
            />
          </Panel>
          {preview && (
            <Panel title="Dividend and early exercise" actions={termHelp('calls_dividend')}>
              {dividend ? (
                <Stack gap={1}>
                  <Text>{`Next ex-dividend date ${dividend.exDate}, ${dividend.amount} a share.`}</Text>
                  <Text>{`Own the shares by ${dividend.ownBy} to collect it.`}</Text>
                </Stack>
              ) : preview.dividend_unknown ? (
                <GapLine gap={preview.dividend_unknown} />
              ) : null}
            </Panel>
          )}
        </>
      )}
      <CalculatorFooter />
    </Stack>
  );
}
