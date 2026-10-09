/** The app: providers around the router. Composition only (ADR 0025). */
import { RouterProvider } from '@tanstack/react-router';
import { useEffect, useState } from 'react';

import { TermHelpProvider } from '@/entities/availability';
import { GuideHelp, GuideHelpProvider } from '@/features/guide-help';

import { AppProviders, createQueryClient, startQueryPersistence } from './providers';
import { router } from './router';

export function App() {
  // One query client for the providers and, through the router context, the route guards.
  const [queryClient] = useState(createQueryClient);
  // After the first paint: restore the page cache kept from the last visit, and keep saving it.
  useEffect(() => startQueryPersistence(queryClient), [queryClient]);
  return (
    <AppProviders queryClient={queryClient}>
      <GuideHelpProvider
        navigate={(path) => {
          router.history.push(path);
        }}
      >
        <TermHelpProvider render={(id) => <GuideHelp entry={{ kind: 'term', id }} />}>
          <RouterProvider router={router} context={{ queryClient }} />
        </TermHelpProvider>
      </GuideHelpProvider>
    </AppProviders>
  );
}
