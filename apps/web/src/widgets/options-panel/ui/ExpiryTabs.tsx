/**
 * The chain's expiries as tabs (a window of seven around the chosen one) with a select for
 * every listed expiry; the chain table is the tab's content.
 */
import { Select, Stack, Tabs } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { expiryLabel } from '@/entities/chain';

const TAB_COUNT = 7;
/** Tabs before the chosen expiry (the rest come after it). */
const BEFORE = 2;

export interface ExpiryTabsProps {
  session: string;
  expiries: readonly string[];
  value: string;
  onChange: (expiry: string) => void;
  children: ReactNode;
}

export function ExpiryTabs({ session, expiries, value, onChange, children }: ExpiryTabsProps) {
  const upcoming = expiries.filter((e) => e >= session);
  const at = Math.max(0, upcoming.indexOf(value));
  const first = Math.max(0, Math.min(at - BEFORE, upcoming.length - TAB_COUNT));
  const shown = upcoming.slice(first, first + TAB_COUNT);
  if (!shown.includes(value)) shown.push(value);
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={2} align="center" justify="between" wrap>
        <Tabs
          label="Expiry"
          size="sm"
          items={shown.map((e) => ({ id: e, label: expiryLabel(session, e) }))}
          value={value}
          onChange={onChange}
        />
        <Select
          aria-label="All expiries"
          size="sm"
          width="auto"
          options={upcoming.map((e) => ({ value: e, label: expiryLabel(session, e) }))}
          value={value}
          onValueChange={onChange}
        />
      </Stack>
      {children}
    </Stack>
  );
}
