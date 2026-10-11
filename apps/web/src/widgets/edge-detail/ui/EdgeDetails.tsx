/**
 * Details of an edge, behind one Disclosure: the verdict's tests, the backtests and the figures
 * behind the verdict. The body loads on first open, so the page's first paint stays small.
 */
import { Disclosure } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import type { Edge } from '@/entities/edge';

import { EdgeDetailsBody } from './EdgeDetailsBody';

export interface EdgeDetailsProps {
  edge: Edge;
  /** More sections of the details (the page composes them), shown with the body once opened. */
  children?: ReactNode;
}

export function EdgeDetails({ edge, children }: EdgeDetailsProps) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure
      label="Details"
      count={String(edge.verdict.criteria.length)}
      open={open}
      onOpenChange={setOpen}
    >
      {open && (
        <>
          <EdgeDetailsBody edge={edge} />
          {children}
        </>
      )}
    </Disclosure>
  );
}
