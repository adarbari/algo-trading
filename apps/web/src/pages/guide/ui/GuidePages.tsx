/**
 * The Guide's pages (ADR 0051): the home (`/guide`), the field index (`/guide/fields`) and one
 * field's page (`/guide/fields/$name`). Each is the reference frame (a rail on the side, the
 * article, and on a field page the "On this page" list) around one widget; the choices (view,
 * theme, intent, field) come from the route as props.
 */
import { DocLayout } from '@algotrade/ui';

import type { FieldsSearch, FieldsView } from '@/entities/guide';
import { GuideFieldsIndex } from '@/widgets/guide-fields';
import { FieldOutline, GuideField } from '@/widgets/guide-field';
import { GuideHome } from '@/widgets/guide-home';
import { GuideRail } from '@/widgets/guide-rail';

export function GuideHomePage() {
  return (
    <DocLayout rail={<GuideRail page="home" />}>
      <GuideHome />
    </DocLayout>
  );
}

export interface GuideFieldsPageProps extends FieldsSearch {
  onViewChange: (view: FieldsView) => void;
}

export function GuideFieldsPage({ view, theme, intent, onViewChange }: GuideFieldsPageProps) {
  return (
    <DocLayout rail={<GuideRail page="fields" theme={theme} />}>
      <GuideFieldsIndex view={view} theme={theme} intent={intent} onViewChange={onViewChange} />
    </DocLayout>
  );
}

export interface GuideFieldPageProps {
  /** The catalogue name in the URL. */
  name: string;
  /** Opens the Screener Builder. */
  onAddToBuilder: () => void;
}

export function GuideFieldPage({ name, onAddToBuilder }: GuideFieldPageProps) {
  return (
    <DocLayout rail={<GuideRail page="field" field={name} />} aside={<FieldOutline />}>
      <GuideField name={name} onAddToBuilder={onAddToBuilder} />
    </DocLayout>
  );
}
