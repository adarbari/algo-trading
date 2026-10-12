/**
 * The accepted formulas on the Feature requests page, in its own lazy chunk so the ranked list
 * above it paints first and the page's budget holds.
 */
import { AcceptedFormulaList } from '@/widgets/accepted-formula-list';

export default function AcceptedFormulasSection() {
  return <AcceptedFormulaList />;
}
