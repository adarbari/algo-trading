/** The Guide button the page supplies (a feature may not import another): `help(term)` renders
 * the InfoButton of a glossary term beside what it explains. */
import { createContext, useContext, type ReactNode } from 'react';

export type HelpFor = (term: string) => ReactNode;

const HelpContext = createContext<HelpFor>(() => null);

export const HelpProvider = HelpContext.Provider;
export const useHelp = (): HelpFor => useContext(HelpContext);
