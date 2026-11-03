/**
 * "Add a ticker": the symbol and an optional note. The server resolves the ticker through the
 * symbol resolver and answers a refusal when it does not resolve or the caller is not an admin;
 * the form shows that detail as sent. A repeat (already listed) says so.
 */
import { Banner, Button, Field, Input, Mono, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { isTicker } from '@/entities/event-scope';
import { errorDetail } from '@/shared/api';

import { useAddScopeName } from '../api/hooks';

export function AddScopeNameForm() {
  const [symbol, setSymbol] = useState('');
  const [note, setNote] = useState('');
  const add = useAddScopeName();
  const result = add.data;
  const symbolError =
    symbol !== '' && !isTicker(symbol) ? 'Use a ticker such as AAPL or BRK.B.' : undefined;
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} wrap align="end">
        <Field label="Ticker" {...(symbolError ? { error: symbolError } : {})}>
          <Input
            value={symbol}
            onValueChange={setSymbol}
            mono
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
        <Field label="Note (optional)">
          <Input value={note} onValueChange={setNote} autoComplete="off" maxLength={200} />
        </Field>
        <Button
          variant="primary"
          disabled={!isTicker(symbol)}
          loading={add.isPending}
          onClick={() => {
            add.mutate(
              { symbol, note },
              {
                onSuccess: () => {
                  setSymbol('');
                  setNote('');
                },
              },
            );
          }}
        >
          Add
        </Button>
      </Stack>
      {add.error && <Banner tone="negative">{errorDetail(add.error)}</Banner>}
      {result && (
        <Banner tone="info">
          <Mono>{result.symbol}</Mono> {result.changed ? 'was added.' : 'was already listed.'}
        </Banner>
      )}
    </Stack>
  );
}
