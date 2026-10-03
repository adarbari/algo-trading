/**
 * Stylelint for design-system CSS (ADR 0011 style, ADR 0025 rule 3). Styling exists only in
 * design-system/; every value comes from a token (var(--...)), and the banned "AI dashboard"
 * look (gradients, glows, shadows, raw colours, one-off sizes) fails here.
 */
const guide = 'See docs/ui/design-system.md and docs/ui/architecture.md (ADR 0011, ADR 0025).';
const msg = (text) => ({ message: `${text} ${guide}` });

export default {
  extends: ['stylelint-config-standard', 'stylelint-config-css-modules'],
  plugins: ['stylelint-declaration-strict-value'],
  ignoreFiles: [
    'design-system/tokens/tokens.css',
    'node_modules/**',
    'dist/**',
    'storybook-static/**',
  ],
  rules: {
    'color-no-hex': [true, msg('No hex colours: use a colour token, var(--color-...).')],
    'color-named': ['never', msg('No named colours: use a colour token, var(--color-...).')],
    'function-disallowed-list': [
      [
        'linear-gradient',
        'radial-gradient',
        'conic-gradient',
        'repeating-linear-gradient',
        'repeating-radial-gradient',
        'rgb',
        'rgba',
        'hsl',
        'hsla',
        'oklch',
        'color-mix',
      ],
      msg('No gradients or raw colour functions: use colour tokens.'),
    ],
    'property-disallowed-list': [
      ['box-shadow', 'text-shadow', 'filter', 'backdrop-filter'],
      msg(
        'No shadows, glows or filters: separate surfaces with borders (var(--border-width-thin) solid var(--color-border-subtle)).',
      ),
    ],
    'unit-disallowed-list': [
      ['px', 'rem', 'em', 'pt', 'vh', 'vw'],
      msg('No one-off sizes: use space, size, radius and density tokens.'),
    ],
    'scale-unlimited/declaration-strict-value': [
      [
        '/color$/',
        'fill',
        'stroke',
        'background',
        'font-size',
        'font-family',
        'font-weight',
        'line-height',
        'z-index',
        'border-radius',
        'gap',
        'row-gap',
        'column-gap',
        'transition-duration',
      ],
      {
        ignoreValues: [
          'transparent',
          'currentcolor',
          'inherit',
          'none',
          '0',
          'auto',
          'initial',
          'unset',
        ],
        disableFix: true,
        message: `Use a token (var(--...)) for "\${property}". ${guide}`,
      },
    ],
    'selector-max-type': [
      0,
      msg('Style components through their own class (CSS Modules), never element selectors.'),
    ],
    'selector-max-id': [0, msg('No id selectors.')],
    'declaration-no-important': [true, msg('No !important.')],
    'selector-class-pattern': [
      '^[a-z][a-zA-Z0-9]*$',
      msg('Class names are camelCase (CSS Modules).'),
    ],
  },
  overrides: [
    {
      // The one global stylesheet: base element styles applied by UiProvider.
      files: ['design-system/theme/base.css'],
      rules: { 'selector-max-type': null },
    },
  ],
};
