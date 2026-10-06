/**
 * The Builder's "Describe it" box: the describe form over the Builder's working document; the
 * draft the model proposes replaces it as an unsaved edit (save, preview and finalise as usual).
 * Shown once the screen is loaded.
 */
import { Panel } from '@algotrade/ui';

import { useScreenerBuilder } from '@/features/screener-builder';
import { DescribeForm } from '@/features/screener-describe';

export function DescribeScreen() {
  const builder = useScreenerBuilder();
  if (builder.status !== 'ready') return null;
  return (
    <Panel title="Describe it" description="A sentence becomes draft criteria you review">
      <DescribeForm
        screenerId={builder.id}
        document={builder.document}
        onDraft={builder.loadDocument}
      />
    </Panel>
  );
}
