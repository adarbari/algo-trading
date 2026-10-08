/**
 * The viewer's snoozes as a hook: `visible(items)` drops the issues snoozed and not yet back,
 * `snooze(id)` hides one for 24 hours and remembers it in this browser.
 */
import { useCallback, useState } from 'react';

import { loadSnoozes, saveSnoozes, withSnooze, type Snoozes } from './snooze';

export interface UseSnooze {
  visible: <T extends { id: string }>(items: readonly T[]) => T[];
  snooze: (id: string) => void;
}

export function useSnooze(now: () => number = Date.now): UseSnooze {
  const [snoozes, setSnoozes] = useState<Snoozes>(() => loadSnoozes(now()));
  const snooze = useCallback(
    (id: string) => {
      const next = withSnooze(snoozes, id, now());
      saveSnoozes(next);
      setSnoozes(next);
    },
    [snoozes, now],
  );
  const visible = useCallback(
    <T extends { id: string }>(items: readonly T[]): T[] =>
      items.filter((item) => (snoozes[item.id] ?? 0) <= now()),
    [snoozes, now],
  );
  return { visible, snooze };
}
