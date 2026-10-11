/**
 * The recent calls beside the chosen call's detail. The page loads it as one lazy chunk: the
 * list, its failures view and the failure detail are not needed to paint the spend panels.
 */
import { MasterDetail } from '@algotrade/ui';

import { UsageCallDetail } from '@/widgets/usage-call-detail';
import { UsageCallsPanel } from '@/widgets/usage-calls-panel';

export interface CallsSectionProps {
  selected: string | null;
  onSelectCall: (id: string) => void;
  onClearCall: () => void;
}

export default function CallsSection({ selected, onSelectCall, onClearCall }: CallsSectionProps) {
  return (
    <MasterDetail
      columns="main-aside"
      collapse="lg"
      master={<UsageCallsPanel selected={selected} onSelect={onSelectCall} />}
      detail={<UsageCallDetail selected={selected} />}
      detailKey={selected}
      detailTitle="Call detail"
      onDetailClose={onClearCall}
    />
  );
}
