/**
 * The help button for a Guide entry and the drawer it opens (ADR 0051, docs/ui/guide.md
 * "The help drawer"): an `InfoButton` whose hover is the entry's first sentence and whose click
 * opens the entry's first sections and "Open full page". The kind picks the sections: a field
 * (how to read it, what to use it for, "Use this" when the page passes `onUse`), a regime
 * indicator (why it matters, when it is on, lead time and track record) or a reference market
 * fall (dates, drawdowns, cause), a glossary term (its short line and its body) or a Start here
 * page (its summary and first section). The text is the server's; nothing is written here.
 */
import type { GuideUse } from '@/entities/feature';

import type { GuideEntry } from '../model/entry';
import { EpisodeHelp } from './EpisodeHelp';
import { FieldHelp } from './FieldHelp';
import { IndicatorHelp } from './IndicatorHelp';
import { StartHelp } from './StartHelp';
import { TermHelp } from './TermHelp';

export interface GuideHelpProps {
  /** The Guide entry the button explains. */
  entry: GuideEntry;
  /**
   * Field entries: set the thing being edited to one of the field's intents (a criterion row in
   * the Builder). Each intent shows "Use this" only when given; the drawer closes so the change
   * is seen.
   */
  onUse?: (use: GuideUse) => void;
  /** Field entries: the "Use this" buttons are inert (a read-only form). */
  useDisabled?: boolean;
}

export function GuideHelp({ entry, onUse, useDisabled = false }: GuideHelpProps) {
  switch (entry.kind) {
    case 'field':
      return <FieldHelp name={entry.id} onUse={onUse} useDisabled={useDisabled} />;
    case 'indicator':
      return <IndicatorHelp indicatorKey={entry.id} />;
    case 'episode':
      return <EpisodeHelp episodeKey={entry.id} />;
    case 'term':
      return <TermHelp id={entry.id} />;
    case 'start':
      return <StartHelp id={entry.id} />;
  }
}
