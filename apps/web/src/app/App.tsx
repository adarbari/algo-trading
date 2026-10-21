/** The app: providers around the router. Composition only (ADR 0025). */
import { RouterProvider } from '@tanstack/react-router';
import { useState } from 'react';

import { TermHelpProvider } from '@/entities/availability';
import { GuideHelp, GuideHelpProvider } from '@/features/guide-help';

import { AppProviders, createQueryClient } from './providers';
import { router, startEarlyReads } from './router';

export function App() {
  // One query client for the providers and, through the router context, the route guards.
  const [queryClient] = useState(() => {
    const client = createQueryClient();
    startEarlyReads(client);
    return client;
  });
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
