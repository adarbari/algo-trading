/**
 * The one helper that renders a glossary term's help button (an `InfoButton` that opens the
 * term in the Guide drawer) beside what it explains: `termHelp('win_rate')`. Every file that
 * needs one calls this instead of building its own (ADR 0051; the fitness test
 * tests/architecture/guide/ recognises exactly this name).
 */
import { GuideHelp } from './GuideHelp';

export const termHelp = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;
