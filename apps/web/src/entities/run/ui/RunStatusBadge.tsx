/** A run, step, item or check status as a badge: the recorded words, toned by what they mean. */
import { StatusBadge } from '@algotrade/ui';

import { statusTone } from '../model/status';

export function RunStatusBadge({ status, title }: { status: string; title?: string }) {
  const code = status.split(':', 1)[0]?.trim() ?? status;
  const hover = title ?? (status === code ? undefined : status);
  return (
    <StatusBadge tone={statusTone(code)} {...(hover ? { title: hover } : {})}>
      {code.toUpperCase()}
    </StatusBadge>
  );
}
