/**
 * A table column with its help button: where a column factory named a Guide entry (`help`), the
 * header gets the `GuideHelp` button (`headerAction`). Every table of catalogue fields uses it,
 * so each field header explains itself the same way (ADR 0051).
 */
import type { HelpedColumn } from '@/entities/feature';

import { GuideHelp } from './GuideHelp';

export function helped<R>({ help, ...column }: HelpedColumn<R>): Omit<HelpedColumn<R>, 'help'> {
  return help ? { ...column, headerAction: <GuideHelp entry={help} /> } : column;
}
