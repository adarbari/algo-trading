/**
 * How a Guide term's help button is drawn here. An entity cannot import the help feature, so the
 * app provides the renderer (`GuideHelp` for `{ kind: 'term', id }`) once; without a provider
 * (a unit test, a story) no button is drawn and the note still reads.
 */
import { createContext, useContext, type ReactNode } from 'react';

export type RenderTermHelp = (termId: string) => ReactNode;

const TermHelpContext = createContext<RenderTermHelp | null>(null);

export function TermHelpProvider({
  render,
  children,
}: {
  render: RenderTermHelp;
  children: ReactNode;
}) {
  return <TermHelpContext value={render}>{children}</TermHelpContext>;
}

/** The help button for a glossary term, or nothing where no renderer is provided. */
export function useTermHelp(): RenderTermHelp {
  return useContext(TermHelpContext) ?? (() => null);
}
