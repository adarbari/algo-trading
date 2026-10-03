/**
 * Foundations/Tokens: the documented token set (FINAL, approved mockups 2026-10-03). Colour
 * swatches follow the active theme (toolbar); hex values and contrast ratios are listed for both
 * themes, computed from the typed tokens. Every story is screenshotted and axe-checked in light
 * and dark like any component.
 */
import type { Meta, StoryObj } from '@storybook/react-vite';
import type { CSSProperties } from 'react';

import { Heading } from '../primitives/Heading';
import { Mono } from '../primitives/Mono';
import { Stack } from '../primitives/Stack';
import { Text } from '../primitives/Text';
import {
  AA_GRAPHIC,
  AA_TEXT,
  colorRoles,
  contrastRatio,
  dark,
  density,
  fontSize,
  fontWeight,
  light,
  radius,
  SERIES,
  space,
  spaceName,
  textPairs,
  type Space,
} from '../tokens';
import styles from './Tokens.module.css';

const meta = {
  title: 'Foundations/Tokens',
  parameters: { layout: 'padded' },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** A custom property for the swatch / bar classes (the value is always a token var). */
function cssVar(name: string, value: string): CSSProperties {
  const style: Record<string, string> = { [name]: value };
  return style;
}

const darkRoles = new Map(colorRoles(dark, 'standard'));
const lightRoles = new Map(colorRoles(light, 'standard'));

function Swatch({ role }: { role: string }) {
  return <span className={styles.swatch} style={cssVar('--swatch', `var(--color-${role})`)} />;
}

function minRatio(fg: string, bgs: string[]): number {
  return Math.min(...bgs.map((bg) => contrastRatio(fg, bg)));
}

/** Every colour role: swatch (active theme), dark and light hex. */
export const Colors: Story = {
  render: () => (
    <Stack gap={3}>
      <Heading level={1}>Colour roles</Heading>
      <Text as="p" tone="secondary">
        Components use only these roles (var(--color-role)); one accent, borders not shadows.
      </Text>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.head} scope="col">
              Swatch
            </th>
            <th className={styles.head} scope="col">
              Role
            </th>
            <th className={styles.head} scope="col">
              Dark
            </th>
            <th className={styles.head} scope="col">
              Light
            </th>
          </tr>
        </thead>
        <tbody>
          {[...darkRoles.keys()].map((role) => (
            <tr key={role}>
              <td className={styles.cell}>
                <Swatch role={role} />
              </td>
              <td className={styles.cell}>
                <Mono size="md">--color-{role}</Mono>
              </td>
              <td className={styles.cell}>
                <Mono size="md" tone="secondary">
                  {darkRoles.get(role)}
                </Mono>
              </td>
              <td className={styles.cell}>
                <Mono size="md" tone="secondary">
                  {lightRoles.get(role)}
                </Mono>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Stack>
  ),
};

/** WCAG contrast of every text role on the backgrounds it is used on (the minimum). */
export const Contrast: Story = {
  render: () => (
    <Stack gap={3}>
      <Heading level={1}>Text contrast (WCAG AA 4.5:1)</Heading>
      <Text as="p" tone="secondary">
        Lowest ratio of each text role over bg, surface and row (status colours also over their own
        tint). Tested in tokens.test.ts; axe checks every story in both themes.
      </Text>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.head} scope="col">
              Text role
            </th>
            <th className={styles.head} scope="col">
              Dark
            </th>
            <th className={styles.head} scope="col">
              Light
            </th>
          </tr>
        </thead>
        <tbody>
          {textPairs(dark).map((pair, i) => {
            const lightPair = textPairs(light)[i];
            const d = minRatio(pair.fg, pair.bgs);
            const l = lightPair ? minRatio(lightPair.fg, lightPair.bgs) : 0;
            return (
              <tr key={pair.fgName}>
                <td className={styles.cell}>
                  <Mono size="md">{pair.fgName}</Mono>
                </td>
                <td className={styles.cell}>
                  <Text size="md" tone={d >= AA_TEXT ? 'default' : 'negative'}>
                    {d.toFixed(2)}:1
                  </Text>
                </td>
                <td className={styles.cell}>
                  <Text size="md" tone={l >= AA_TEXT ? 'default' : 'negative'}>
                    {l.toFixed(2)}:1
                  </Text>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Stack>
  ),
};

/** The data-visualisation series, in fixed order; graphic contrast over surface. */
export const Series: Story = {
  render: () => (
    <Stack gap={3}>
      <Heading level={1}>Series palette</Heading>
      <Text as="p" tone="secondary">
        Assign in this order by entity, never cycled. Distinct in hue and lightness; validated for
        colour-vision deficiency (see docs/ui/design-system.md).
      </Text>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.head} scope="col">
              Swatch
            </th>
            <th className={styles.head} scope="col">
              Series
            </th>
            <th className={styles.head} scope="col">
              Dark (vs surface)
            </th>
            <th className={styles.head} scope="col">
              Light (vs surface)
            </th>
          </tr>
        </thead>
        <tbody>
          {SERIES.map((s) => (
            <tr key={s}>
              <td className={styles.cell}>
                <Swatch role={s} />
              </td>
              <td className={styles.cell}>
                <Mono size="md">--color-{s}</Mono>
              </td>
              {[dark, light].map((p) => {
                const ratio = contrastRatio(p.series[s], p.surface.surface);
                return (
                  <td className={styles.cell} key={p.surface.bg}>
                    <Mono size="md" tone="secondary">
                      {p.series[s]}
                    </Mono>{' '}
                    <Text size="md" tone={ratio >= AA_GRAPHIC ? 'default' : 'negative'}>
                      {ratio.toFixed(2)}:1
                    </Text>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Stack>
  ),
};

/** IBM Plex Sans scale and weights; IBM Plex Mono. */
export const Typography: Story = {
  render: () => (
    <Stack gap={3}>
      <Heading level={1}>Type scale</Heading>
      <Stack gap={2}>
        {(Object.keys(fontSize) as (keyof typeof fontSize)[]).map((key) => (
          <Stack key={key} direction="row" gap={4} align="baseline">
            <Mono size="sm" tone="muted">
              {key} {fontSize[key].size}/{fontSize[key].lineHeight}
            </Mono>
            <Text size={key}>Completeness 96.4% · 4,203 underlyings</Text>
          </Stack>
        ))}
      </Stack>
      <Heading level={2}>Weights</Heading>
      <Stack direction="row" gap={4}>
        {(Object.keys(fontWeight) as (keyof typeof fontWeight)[]).map((w) => (
          <Text key={w} weight={w}>
            {w} {fontWeight[w]}
          </Text>
        ))}
      </Stack>
      <Heading level={2}>Mono</Heading>
      <Mono>SPY 261016P00575000 · 0123456789</Mono>
    </Stack>
  ),
};

/** The 4 px space scale, radii and density. */
export const SpaceAndShape: Story = {
  render: () => (
    <Stack gap={4}>
      <Heading level={1}>Space, radius, density</Heading>
      <Stack gap={1}>
        {(Object.keys(space) as unknown as Space[]).map((step) => (
          <Stack key={step} direction="row" gap={3} align="center">
            <Mono size="sm" tone="muted">
              --space-{spaceName(step)} {space[step]}px
            </Mono>
            <span
              className={styles.bar}
              style={cssVar('--bar', `var(--space-${spaceName(step)})`)}
            />
          </Stack>
        ))}
      </Stack>
      <Stack direction="row" gap={4}>
        {(Object.keys(radius) as (keyof typeof radius)[]).map((r) => (
          <Stack key={r} gap={1} align="center">
            <span className={styles.radius} style={cssVar('--radius', `var(--radius-${r})`)} />
            <Mono size="sm" tone="muted">
              {r} {radius[r]}px
            </Mono>
          </Stack>
        ))}
      </Stack>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.head} scope="col">
              Density
            </th>
            <th className={styles.head} scope="col">
              Control
            </th>
            <th className={styles.head} scope="col">
              Row
            </th>
            <th className={styles.head} scope="col">
              Cell padding
            </th>
            <th className={styles.head} scope="col">
              Panel padding
            </th>
          </tr>
        </thead>
        <tbody>
          {(Object.keys(density) as (keyof typeof density)[]).map((d) => (
            <tr key={d}>
              <td className={styles.cell}>
                <Text size="md">{d}</Text>
              </td>
              <td className={styles.cell}>
                <Text size="md">{density[d].controlHeight}px</Text>
              </td>
              <td className={styles.cell}>
                <Text size="md">{density[d].rowHeight}px</Text>
              </td>
              <td className={styles.cell}>
                <Text size="md">
                  {density[d].cellPaddingY} / {density[d].cellPaddingX}px
                </Text>
              </td>
              <td className={styles.cell}>
                <Text size="md">
                  {density[d].panelPaddingY} / {density[d].panelPaddingX}px
                </Text>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Stack>
  ),
};
