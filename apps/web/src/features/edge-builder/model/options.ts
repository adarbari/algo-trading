/** The choices the steps offer, as the form names them (the server's own ids are the values). */
import type { SelectOption, SegmentedOption } from '@algotrade/ui';

import type { Schedule, Step, Win } from './draft';

export const STEP_LABELS: Record<Step, string> = {
  idea: '1 · Idea',
  screens: '2 · Screens',
  picks: '3 · Picks',
  trade: '4 · Trade',
  compare: '5 · Compare against',
  test: '6 · Test and run',
};

export const SCHEDULES: readonly SegmentedOption<Schedule>[] = [
  { value: 'every_session', label: 'Every session' },
  { value: 'month_end', label: 'Month end' },
  { value: 'on_event', label: 'On an event' },
];

/** The event classes a schedule may trigger on (`config/edges/document.py` EVENT_CLASSES). */
export const EVENTS: readonly SelectOption[] = [
  { value: 'earnings_reaction', label: 'After earnings are reported' },
  { value: 'earnings_expected', label: 'Before earnings are expected' },
  { value: 'ex_dividend', label: 'On an ex-dividend date' },
  { value: 'index_change', label: 'On an S&P 500 membership change' },
  { value: 'macro_release', label: 'On a macro release' },
];

export const TAKES: readonly SegmentedOption<'top' | 'all'>[] = [
  { value: 'top', label: 'Top N' },
  { value: 'all', label: 'All that qualify' },
];

export const WINS: readonly SegmentedOption<Exclude<Win, 'other'>>[] = [
  { value: 'beats', label: 'Beats SPY after costs' },
  { value: 'rises', label: 'Rises after costs' },
];

/** Holding periods offered as chips, in trading days (the edge's own are added to them). */
export const HORIZON_CHOICES = [5, 10, 20, 40, 60, 120] as const;

/** The seven quality-bar answers beyond mechanism and persistence. */
export const QUALITY_LABELS: Record<string, string> = {
  outcome: 'What counts as it working',
  trigger_timing: 'When the trigger is known',
  replication: 'How to replicate it',
  expected_size: 'The size to expect',
  capacity_costs: 'Capacity and costs',
  failure_modes: 'How it fails',
  decoys: 'What else could explain it',
};
