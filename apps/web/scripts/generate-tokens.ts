/** Writes design-system/tokens/tokens.css from the typed token sources (`npm run tokens`). */
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { renderTokensCss } from '../design-system/tokens/css';

const target = fileURLToPath(new URL('../design-system/tokens/tokens.css', import.meta.url));
writeFileSync(target, renderTokensCss());
console.log(`tokens: wrote ${target}`);
