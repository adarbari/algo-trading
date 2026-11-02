/**
 * Trader > an idea (`/ideas/$symbol?setup=`): the name a qualifying setup picked, its sections
 * filled from the setup (ADR 0083 amendment (b)). The page only composes the widget.
 */
import { Stack } from '@algotrade/ui';

import { IdeaDetail } from '@/widgets/idea-detail';

export interface IdeaPageProps {
  symbol: string;
  setup: string | undefined;
  onSetupChange: (edgeId: string) => void;
  onOpenEdge: (edgeId: string) => void;
  onOpenTicker: (symbol: string) => void;
  onBack: (tab: string) => void;
}

export function IdeaPage(props: IdeaPageProps) {
  return (
    <Stack gap={3}>
      <IdeaDetail {...props} />
    </Stack>
  );
}
