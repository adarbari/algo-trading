/** A call's cost basis and outcome as badges: the stored words, toned by what they mean. */
import { StatusBadge } from '@algotrade/ui';

import { BASIS_LABEL, basisTone, outcomeTone } from '../model/labels';

export function BasisBadge({ basis }: { basis: string }) {
  return <StatusBadge tone={basisTone(basis)}>{BASIS_LABEL[basis] ?? basis}</StatusBadge>;
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  return <StatusBadge tone={outcomeTone(outcome)}>{outcome.replace('_', ' ')}</StatusBadge>;
}
