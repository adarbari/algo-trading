/** The app: providers around the router. Composition only (ADR 0025). */
import { RouterProvider } from '@tanstack/react-router';

import { AppProviders } from './providers';
import { router } from './router';

export function App() {
  return (
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
