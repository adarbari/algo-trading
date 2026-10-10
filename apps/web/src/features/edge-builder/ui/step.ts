import type { EdgeDraft } from '../model/draft';

/** What every step form gets: the one draft and how to change it. */
export interface StepProps {
  draft: EdgeDraft;
  onChange: (patch: Partial<EdgeDraft>) => void;
}
