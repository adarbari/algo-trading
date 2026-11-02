/**
 * The option pick's sections of one idea's page (plan O4), each the server's and never derived
 * here: the plan (the example position the setup's rule would open on tonight's chain, the cash
 * set aside, the declared exits as dollar marks, the premium floor, the chance of finishing in
 * the money, the most you can lose) and the position's risks (theta a day, a one-sigma day, the
 * report and ex-dividend flags). A part the server could not fill says why through its
 * `unknown`; no bid or ask is served.
 */
import {
  formatValue,
  KeyValue,
  Panel,
  Stack,
  StatusBadge,
  Text,
  type KeyValueItem,
} from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import type { IdeaDetail } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

type Option = NonNullable<IdeaDetail['option']>;
type Leg = Option['legs'][number];

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'weekday' }).text;
const dollars = (amount: number, digits = 2) =>
  formatValue(amount, { kind: 'currency', digits }).text;

function legLabel(leg: Leg): string {
  const side = leg.qty < 0 ? 'Short' : 'Long';
  return `${side} ${String(Math.abs(leg.qty))} ${leg.right}`;
}

function legItems(option: Option): KeyValueItem[] {
  return option.legs.map((leg) => ({
    id: `${leg.right}:${String(leg.strike)}:${leg.expiry}`,
    label: legLabel(leg),
    value: `${formatValue(leg.strike, { kind: 'number', digits: 2 }).text} · ${day(leg.expiry)} · ${dollars(leg.mid)} mid`,
    action: termHelp('idea_example_position'),
  }));
}

/** The leg whose chance of ending in the money the plan shows: the first sold, else the first. */
function lead(option: Option): Leg | undefined {
  return option.legs.find((leg) => leg.qty < 0) ?? option.legs[0];
}

function exitItems(option: Option): KeyValueItem[] {
  const items: KeyValueItem[] = [];
  if (option.takeProfitDebit !== null) {
    items.push({
      label: 'Take profit, close at',
      value: dollars(option.takeProfitDebit),
      action: termHelp('idea_option_exits'),
    });
  }
  if (option.stopDebit !== null) {
    items.push({ label: 'Stop, close at', value: dollars(option.stopDebit) });
  }
  if (option.stopLoss !== null) {
    items.push({
      label: 'Stop, loss per contract',
      value: dollars(option.stopLoss, 0),
    });
  }
  if (option.exitDteDate !== null) {
    items.push({ label: 'Close by', value: day(option.exitDteDate) });
  }
  if (option.exitSession !== null) {
    items.push({ label: 'Last day held', value: day(option.exitSession) });
  }
  return items;
}

function planItems(option: Option): KeyValueItem[] {
  const chance = lead(option)?.pItm ?? null;
  const items: KeyValueItem[] = [...legItems(option)];
  if (option.netCredit !== null) {
    items.push({
      label: 'Premium collected',
      value: dollars(option.netCredit),
      action: termHelp('idea_example_position'),
    });
  }
  if (option.cashSetAside !== null) {
    items.push({
      label: 'Cash set aside',
      value: dollars(option.cashSetAside, 0),
      action: termHelp('idea_cash_set_aside'),
    });
  }
  items.push(...exitItems(option));
  if (chance !== null) {
    items.push({
      label: 'Chance of ending in the money',
      value: chance,
      format: { kind: 'percent', digits: 0 },
      action: termHelp('idea_chance_in_the_money'),
    });
  }
  items.push({
    label: 'Most you can lose',
    value: option.unbounded
      ? 'No limit'
      : option.maxLoss === null
        ? 'Not known'
        : dollars(option.maxLoss, 0),
    action: termHelp('idea_most_you_can_lose'),
  });
  return items;
}

export function OptionPlanSection({ option }: { option: Option }) {
  return (
    <Panel title="The plan" actions={termHelp('idea_plan')}>
      <Stack gap={3}>
        {option.unknown ? <UnknownNote unknown={option.unknown} /> : null}
        {option.legs.length > 0 ? (
          <KeyValue label="The plan, per contract" items={planItems(option)} />
        ) : null}
        {option.legs.length > 0 ? (
          option.mondayFloor !== null ? (
            <KeyValue
              label="Monday"
              items={[
                {
                  label: 'Still valid at a premium of',
                  value: `${dollars(option.mondayFloor)} or more`,
                  action: termHelp('idea_monday_floor'),
                },
              ]}
            />
          ) : option.floorUnknown ? (
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="secondary">
                Monday premium floor
              </Text>
              {termHelp('idea_monday_floor')}
              <UnknownNote unknown={option.floorUnknown} />
            </Stack>
          ) : null
        ) : null}
      </Stack>
    </Panel>
  );
}

function flag(label: string, found: boolean | null, when: string | null): KeyValueItem {
  return {
    label,
    value:
      found === null ? (
        'Not known'
      ) : found ? (
        <StatusBadge tone="warning">{when === null ? 'Yes' : `Yes · ${day(when)}`}</StatusBadge>
      ) : (
        'No'
      ),
  };
}

export function OptionRisksSection({ option }: { option: Option }) {
  if (option.legs.length === 0) return null;
  const items: KeyValueItem[] = [
    {
      label: 'Theta, a day',
      value: option.thetaPerDay === null ? 'Not known' : dollars(option.thetaPerDay),
      action: termHelp('idea_theta_day'),
    },
    {
      label: 'A one-sigma day, you lose',
      value: option.oneSigmaLoss === null ? 'Not known' : dollars(option.oneSigmaLoss, 0),
      action: termHelp('idea_one_sigma_loss'),
    },
    {
      ...flag('Reports before expiry', option.reportInLife, option.reportDate),
      action: termHelp('idea_report_in_life'),
    },
    {
      ...flag('Ex-dividend in the trade', option.exDividendInLife, option.exDivDate),
      action: termHelp('idea_ex_dividend'),
    },
  ];
  return (
    <Panel title="The position's risks" actions={termHelp('idea_position_risks')}>
      <Stack gap={3}>
        <KeyValue label="Position risks, per contract" items={items} />
        {option.riskUnknown ? <UnknownNote unknown={option.riskUnknown} /> : null}
        {option.calendarUnknown ? <UnknownNote unknown={option.calendarUnknown} /> : null}
      </Stack>
    </Panel>
  );
}
