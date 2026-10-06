/**
 * App-wide providers: the design-system root (tokens, theme, density), the toast queue (one per
 * app: `useToast()` anywhere below) and the query client.
 */
import { ToastProvider, UiProvider } from '@algotrade/ui';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

export function AppProviders({
  queryClient,
  children,
}: {
  /** The app's one query client (also given to the router, so guards share its cache). */
  queryClient: QueryClient;
  children: ReactNode;
}) {
  return (
    <UiProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ToastProvider>
    </UiProvider>
  );
}
