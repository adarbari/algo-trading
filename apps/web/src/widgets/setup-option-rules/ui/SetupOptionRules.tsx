/**
 * The declared position of an option setup, under "The rules" (ADR 0088): when it decides, the
 * legs, the expiry, the exits and the cash set aside, as label / value rows worded from the
 * structured values the server sends. The page composes it below the share rules (`SetupRules`:
 * idea, screens, picks, sources), which an option setup keeps.
 */
import { Heading, KeyValue, Stack, type KeyValueItem } from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import type { OptionSetup } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { ruleRows } from '../model/rules';

export interface SetupOptionRulesProps {
  /** The setup's name, for the rows' accessible label. */
  name: string;
  setup: OptionSetup;
}

export function SetupOptionRules({ name, setup }: SetupOptionRulesProps) {
  const items: KeyValueItem[] = (setup.rules ? ruleRows(setup.rules) : []).map((row) => ({
    id: row.id,
    label: row.label,
    value: row.value,
    action: termHelp(row.help),
  }));
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={3}>The position</Heading>
        {termHelp('option_rules_position')}
      </Stack>
      {setup.rulesUnknown ? <UnknownNote unknown={setup.rulesUnknown} /> : null}
      {items.length > 0 ? (
        <KeyValue layout="grid" label={`${name} position`} items={items} />
      ) : null}
    </Stack>
  );
}
