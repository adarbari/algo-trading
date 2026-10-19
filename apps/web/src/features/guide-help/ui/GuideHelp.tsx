/**
 * The help button for a Guide entry and the drawer it opens (ADR 0051, docs/ui/guide.md
 * "The help drawer"): an `InfoButton` whose hover is the entry's first sentence and whose click
 * opens the entry's first sections and "Open full page". The kind picks the sections: a field
 * (how to read it, what to use it for, "Use this" when the page passes `onUse`), a regime
 * indicator (why it matters, when it is on, lead time and track record) or a reference market
 * fall (dates, drawdowns, cause), a glossary term (its short line and its body) or a Start here
 * page (its summary and first section), a mechanism or a site edge of the Edges section (its
 * one-line hero and first paragraphs). The text is the server's; nothing is written here.
 */
import type { GuideUse } from '@/entities/feature';

import type { GuideEntry } from '../model/entry';
import { EdgeHelp, MechanismHelp } from './EdgesHelp';
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
    case 'mechanism':
      return <MechanismHelp id={entry.id} />;
    case 'edge':
      return <EdgeHelp id={entry.id} />;
  }
}

/**
 * The one helper that renders a glossary term's help button beside what it explains:
 * `termHelp('win_rate')`. Every file that needs one calls this instead of building its own
 * (ADR 0051; tests/architecture/guide/ recognises exactly this name). It lives here, not in
 * its own module, so it rides in GuideHelp's chunk instead of a shared chunk per page.
 */
export const termHelp = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;
