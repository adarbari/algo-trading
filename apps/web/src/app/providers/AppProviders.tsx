/**
 * App-wide providers: the query client, the design-system root (tokens, density and the user's
 * stored theme, ADR 0085) and the toast queue (one per app: `useToast()` anywhere below).
 */
import { ToastProvider, UiProvider } from '@algotrade/ui';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useTheme } from '@/entities/appearance';
import { useViewer } from '@/entities/viewer';

/** The design-system root with the signed-in user's stored theme (none yet: the page keeps the
 * one its inline script set from this device's copy). */
function Themed({ children }: { children: ReactNode }) {
  const signedIn = Boolean(useViewer().data);
  const theme = useTheme(signedIn);
  return <UiProvider {...(theme ? { theme } : {})}>{children}</UiProvider>;
}

export function AppProviders({
  queryClient,
  children,
}: {
  /** The app's one query client (also given to the router, so guards share its cache). */
  queryClient: QueryClient;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <Themed>
        <ToastProvider>{children}</ToastProvider>
      </Themed>
    </QueryClientProvider>
  );
}
