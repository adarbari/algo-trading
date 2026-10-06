/** The app: providers around the router. Composition only (ADR 0025). */
import { RouterProvider } from '@tanstack/react-router';
import { useState } from 'react';

import { AppProviders, createQueryClient } from './providers';
import { router } from './router';

export function App() {
  // One query client for the providers and, through the router context, the route guards.
  const [queryClient] = useState(createQueryClient);
  return (
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} context={{ queryClient }} />
    </AppProviders>
  );
}
