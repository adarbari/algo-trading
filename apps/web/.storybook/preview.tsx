/**
 * Every story renders inside UiProvider with the theme and density chosen in the toolbar
 * (URL: `&globals=theme:dark;density:comfortable`; the screenshot suite uses it).
 */
import type { Decorator, Preview } from '@storybook/react-vite';

import { UiProvider, type DensityName, type Theme } from '@algotrade/ui';

const withUi: Decorator = (Story, context) => (
  <UiProvider
    theme={context.globals['theme'] as Theme}
    density={context.globals['density'] as DensityName}
  >
    <Story />
  </UiProvider>
);

const preview: Preview = {
  decorators: [withUi],
  initialGlobals: { theme: 'dark', density: 'compact' },
  globalTypes: {
    theme: {
      description: 'Colour theme',
      toolbar: {
        title: 'Theme',
        icon: 'mirror',
        items: ['dark', 'light', 'system'],
        dynamicTitle: true,
      },
    },
    density: {
      description: 'Density',
      toolbar: {
        title: 'Density',
        icon: 'component',
        items: ['compact', 'comfortable'],
        dynamicTitle: true,
      },
    },
  },
  parameters: {
    layout: 'padded',
    controls: { expanded: true },
    a11y: { test: 'error' },
  },
};

export default preview;
