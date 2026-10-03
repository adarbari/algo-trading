/**
 * App-wide providers: the design-system root (tokens, theme, density), the toast queue (one per
 * app: `useToast()` anywhere below) and the query client.
 */
import { ToastProvider, UiProvider } from '@algotrade/ui';
import { QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { createQueryClient } from './query-client';

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  return (
    <UiProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ToastProvider>
    </UiProvider>
  );
}
