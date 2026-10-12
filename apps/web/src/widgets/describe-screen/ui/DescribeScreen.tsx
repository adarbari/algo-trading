/**
 * The Builder's "Describe it" box: the describe form over the Builder's working document; the
 * draft the model proposes replaces it as an unsaved edit (save, preview and finalise as usual).
 * What the model understood is the review panel under the input, loaded as one lazy chunk when an
 * answer arrives. A field the draft names that the catalogue has opens its Guide drawer. The
 * Builder owns what the trader decides on the answer's options (readings, formulas). Retyping one
 * part of the sentence returns the whole merged draft, which becomes the working document and the
 * answer shown (the other parts' decisions and notes stay). Review and
 * add on a proposed formula (here or on its pending row) opens the formula dialog filled in with
 * it; saving goes through the formula feature's own save, then the Builder adds the pending
 * criterion as an active row. Shown once the screen is loaded.
 */
import { Panel, Skeleton } from '@algotrade/ui';
import { lazy, Suspense } from 'react';

import { useFeatureCatalogue } from '@/entities/feature';
import { FormulaFeatureDialog } from '@/features/formula-feature';
import { GuideHelp, termHelp } from '@/features/guide-help';
import { useScreenerBuilder } from '@/features/screener-builder';
import { DescribeForm, hasCriteria } from '@/features/screener-describe';

import { missingDelta } from './NotAvailable';

const DraftReview = lazy(() => import('./DraftReview'));

export function DescribeScreen() {
  const builder = useScreenerBuilder();
  const catalogue = useFeatureCatalogue();
  const known = new Set((catalogue.data ?? []).map((f) => f.name));
  if (builder.status !== 'ready') return null;
  const renderFieldHelp = (field: string) =>
    known.has(field) ? <GuideHelp entry={{ kind: 'field', id: field }} /> : null;
  const reviewing = builder.reviewing;
  return (
    <>
      <Panel title="Describe it" description="A sentence becomes draft criteria you review">
        <DescribeForm
          screenerId={builder.id}
          document={builder.document}
          onDraft={builder.loadDocument}
          draftSessionId={builder.draftSessionId}
          onSession={builder.setDraftSessionId}
          onAnswer={(answer) => {
            builder.setFormulas(answer.formulas ?? []);
            // The gap stays with the screen (finalising does not wait on it), once the draft
            // loaded: an answer with no criteria leaves the screen (and an uncopied preset) alone.
            if (!hasCriteria(answer.document)) return;
            builder.addNotes((answer.missing ?? []).map((item) => item.description));
          }}
          renderTermHelp={termHelp}
          renderReview={({ answer, serial, replaceAnswer }) => (
            <Suspense fallback={<Skeleton lines={3} label="Loading the review" />}>
              <DraftReview
                key={serial}
                answer={answer}
                document={builder.document}
                formulaStates={builder.formulaStates}
                notes={builder.notes}
                onRemoveNote={builder.removeNote}
                onReviewFormula={builder.reviewFormula}
                onSkipFormula={builder.skipFormula}
                onPickReading={(criterion, choice) => {
                  builder.setCriterion(criterion);
                  builder.recordChoice(choice);
                }}
                onAcceptSuggestion={(criterion) => {
                  builder.addSuggested(criterion);
                }}
                onRedrafted={(next, prior, replaced) => {
                  // One part was retyped: the merged draft is the working document and the
                  // answer shown; the other parts' formula decisions and notes stay.
                  replaceAnswer(next);
                  builder.loadDocument(next.document);
                  builder.replaceFormulas(next.formulas ?? [], replaced.formulas);
                  const { gone, added } = missingDelta(prior, next);
                  gone.forEach((note) => {
                    builder.removeNote(note);
                  });
                  builder.addNotes(added);
                }}
                renderFieldHelp={renderFieldHelp}
              />
            </Suspense>
          )}
        />
      </Panel>
      {reviewing && (
        <FormulaFeatureDialog
          key={reviewing.name}
          open
          onOpenChange={(open) => {
            if (!open) builder.closeReview();
          }}
          initial={{
            name: reviewing.name,
            expr: reviewing.expr,
            unit: reviewing.unit,
            description: reviewing.description,
            nullMeaning: reviewing.null_meaning,
          }}
          onSaved={(field) => {
            builder.acceptFormula(reviewing, field);
          }}
        />
      )}
    </>
  );
}
