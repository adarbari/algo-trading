/**
 * The Guide's pages (ADR 0051): the home (`/guide`), Start here (the index and a how-to page),
 * the glossary (the A to Z index and a term's page), the field index (`/guide/fields`) and one
 * field's page (`/guide/fields/$name`), the screener index, a screener family's page and a screener's page, the situation
 * index and a situation's page, the Market regime index and an indicator's and a market fall's page,
 * the Edges index, a mechanism's page and a site edge's page. Each is the reference frame (a rail on the side, the article,
 * and on a field page the "On this page" list) around one widget; the choices (view, theme,
 * intent, field, screener, situation) and where a screener's buttons go come from the route as
 * props.
 */
import { DocLayout } from '@algotrade/ui';

import type { FieldsSearch, FieldsView } from '@/entities/guide';
import { EdgeOutline, GuideEdge } from '@/widgets/guide-edge';
import { GuideEdgesIndex } from '@/widgets/guide-edges';
import { GuideFieldsIndex } from '@/widgets/guide-fields';
import { FieldOutline, GuideField } from '@/widgets/guide-field';
import { GuideGlossaryIndex, GuideTerm } from '@/widgets/guide-glossary';
import { GuideHome } from '@/widgets/guide-home';
import { GuideMechanism, MechanismOutline } from '@/widgets/guide-mechanism';
import { GuideScreener } from '@/widgets/guide-screener';
import { GuideScreenerCategory } from '@/widgets/guide-screener-category';
import { GuideScreenersIndex } from '@/widgets/guide-screeners';
import { GuideRail } from '@/widgets/guide-rail';
import { GuideEpisode, GuideIndicator, GuideRegimeIndex } from '@/widgets/guide-regime';
import { GuideSituation, GuideSituationsIndex } from '@/widgets/guide-situations';
import { GuideStart, GuideStartIndex, StartOutline } from '@/widgets/guide-start';

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

export function GuideScreenersPage() {
  return (
    <DocLayout rail={<GuideRail page="screeners" />}>
      <GuideScreenersIndex />
    </DocLayout>
  );
}

export function GuideScreenerCategoryPage({ id }: { id: string }) {
  return (
    <DocLayout rail={<GuideRail page="screener_category" category={id} />}>
      <GuideScreenerCategory id={id} />
    </DocLayout>
  );
}

export interface GuideScreenerPageProps {
  /** The preset id in the URL. */
  id: string;
  /** Opens that screener's results. */
  onSeeHits: () => void;
  /** Opens the preset in the Builder. */
  onOpenBuilder: () => void;
}

export function GuideScreenerPage({ id, onSeeHits, onOpenBuilder }: GuideScreenerPageProps) {
  return (
    <DocLayout rail={<GuideRail page="screener" screener={id} />}>
      <GuideScreener id={id} onSeeHits={onSeeHits} onOpenBuilder={onOpenBuilder} />
    </DocLayout>
  );
}

export function GuideSituationsPage() {
  return (
    <DocLayout rail={<GuideRail page="situations" />}>
      <GuideSituationsIndex />
    </DocLayout>
  );
}

export function GuideSituationPage({ slug }: { slug: string }) {
  return (
    <DocLayout rail={<GuideRail page="situation" situation={slug} />}>
      <GuideSituation slug={slug} />
    </DocLayout>
  );
}

export function GuideRegimePage() {
  return (
    <DocLayout rail={<GuideRail page="regime" />}>
      <GuideRegimeIndex />
    </DocLayout>
  );
}

export function GuideIndicatorPage({ indicatorKey }: { indicatorKey: string }) {
  return (
    <DocLayout rail={<GuideRail page="indicator" indicator={indicatorKey} />}>
      <GuideIndicator indicatorKey={indicatorKey} />
    </DocLayout>
  );
}

export function GuideEpisodePage({ slug }: { slug: string }) {
  return (
    <DocLayout rail={<GuideRail page="episode" episode={slug} />}>
      <GuideEpisode slug={slug} />
    </DocLayout>
  );
}

export interface GuideEdgesPageProps {
  /** Opens the live Edges page. */
  onOpenEdgesPage: () => void;
}

export function GuideEdgesPage({ onOpenEdgesPage }: GuideEdgesPageProps) {
  return (
    <DocLayout rail={<GuideRail page="edges" />}>
      <GuideEdgesIndex onOpenEdgesPage={onOpenEdgesPage} />
    </DocLayout>
  );
}

export function GuideMechanismPage({ id }: { id: string }) {
  return (
    <DocLayout rail={<GuideRail page="mechanism" mechanism={id} />} aside={<MechanismOutline />}>
      <GuideMechanism id={id} />
    </DocLayout>
  );
}

export interface GuideEdgePageProps {
  /** The site edge id in the URL. */
  id: string;
  /** Opens that edge's live evidence on the Edges page. */
  onSeeEvidence: () => void;
}

export function GuideEdgePage({ id, onSeeEvidence }: GuideEdgePageProps) {
  return (
    <DocLayout rail={<GuideRail page="edge" />} aside={<EdgeOutline />}>
      <GuideEdge id={id} onSeeEvidence={onSeeEvidence} />
    </DocLayout>
  );
}

export function GuideStartIndexPage() {
  return (
    <DocLayout rail={<GuideRail page="start" />}>
      <GuideStartIndex />
    </DocLayout>
  );
}

export function GuideStartPage({ id }: { id: string }) {
  return (
    <DocLayout
      rail={<GuideRail page="start_page" startPage={id} />}
      aside={<StartOutline id={id} />}
    >
      <GuideStart id={id} />
    </DocLayout>
  );
}

export function GuideGlossaryPage() {
  return (
    <DocLayout rail={<GuideRail page="glossary" />}>
      <GuideGlossaryIndex />
    </DocLayout>
  );
}

export function GuideTermPage({ id }: { id: string }) {
  return (
    <DocLayout rail={<GuideRail page="term" />}>
      <GuideTerm id={id} />
    </DocLayout>
  );
}
