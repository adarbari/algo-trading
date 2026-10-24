/**
 * The pill's popover, loaded by the pill's first click and open from the start: the floating
 * panel (anchored to the same badge) holding the detail, whose read starts now. Lazy, so neither
 * the floating-panel code nor the detail is in the entry chunk.
 */
import { Popover } from '@algotrade/ui';

import type { PillView } from '@/entities/system-status';

import DataStatusPanel from './DataStatusPanel';
import { PillButton } from './DataStatusPill';

export function DataStatusPopover({ data, admin }: { data: PillView; admin: boolean }) {
  return (
    <Popover
      label="Data status"
      placement="bottom-end"
      width="wide"
      defaultOpen
      trigger={(props) => <PillButton data={data} {...props} />}
    >
      <DataStatusPanel admin={admin} />
    </Popover>
  );
}

export default DataStatusPopover;
