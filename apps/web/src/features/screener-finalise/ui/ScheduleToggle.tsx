/** The nightly schedule: its own switch, apart from finalising (a version runs only when this is on). */
import { Checkbox } from '@algotrade/ui';

import { useSetSchedule } from '../api/hooks';

export interface ScheduleToggleProps {
  screenerId: string;
  schedule: string | null;
  /** The screen has a finalised version (only then can it be scheduled). */
  finalised: boolean;
}

export function ScheduleToggle({ screenerId, schedule, finalised }: ScheduleToggleProps) {
  const set = useSetSchedule(screenerId);
  return (
    <Checkbox
      label="Run nightly"
      description={
        finalised
          ? 'Runs the latest finalised version after each nightly update'
          : 'Finalize a version first'
      }
      checked={(set.isPending ? set.variables : schedule) === 'nightly'}
      disabled={!finalised || set.isPending}
      onCheckedChange={(on) => {
        set.mutate(on ? 'nightly' : null);
      }}
    />
  );
}
