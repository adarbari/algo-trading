/**
 * PhoneFold: secondary content that is shown in place on a wide container and folds behind a
 * `Disclosure` summary under `sm`, so a phone reaches the first row of a table sooner (ADR 0052).
 * It measures its own width (a container, not the viewport) and keeps the same children in both.
 */
import type { ReactNode } from 'react';

import { useNarrow } from '../../responsive';
import { Disclosure } from '../Disclosure';

export interface PhoneFoldProps {
  /** The summary of the folded form. */
  label: ReactNode;
  /** A count or short value at the end of the summary. */
  count?: ReactNode;
  /** The content: shown in place when wide, behind the summary when narrow. */
  children: ReactNode;
}

export function PhoneFold({ label, count, children }: PhoneFoldProps) {
  const [ref, isNarrow] = useNarrow('sm');
  return (
    <div ref={ref}>
      {isNarrow ? (
        <Disclosure label={label} count={count}>
          {children}
        </Disclosure>
      ) : (
        children
      )}
    </div>
  );
}
