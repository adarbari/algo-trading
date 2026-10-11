/**
 * One section of an edge's page below its head: the element the section navigation scrolls to,
 * holding the section's chunk and its data until it nears the viewport (`LazySection`), with a
 * placeholder of the section's height while its code loads.
 */
import { Box, LazySection, Skeleton, type LazySectionProps } from '@algotrade/ui';
import { Suspense, type ReactNode } from 'react';

export interface EdgeSectionProps {
  /** The element id the section navigation points to. */
  id: string;
  /** The section's name (what the placeholder says is loading). */
  label: string;
  /** The block size the placeholder reserves. */
  size?: LazySectionProps['minBlockSize'];
  children: ReactNode;
}

export function EdgeSection({ id, label, size = 'lg', children }: EdgeSectionProps) {
  return (
    <Box id={id}>
      <LazySection label={label} minBlockSize={size}>
        <Suspense fallback={<Skeleton variant="rect" height="lg" label={`Loading ${label}`} />}>
          {children}
        </Suspense>
      </LazySection>
    </Box>
  );
}
