/** App-wide providers: the design-system root (tokens, theme, density) and the query client. */
import { UiProvider } from '@algotrade/ui';
import { QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { createQueryClient } from './query-client';

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  return (
    <UiProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </UiProvider>
  );
}
