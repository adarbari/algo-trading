/**
 * Entity: the signed-in user (ADR 0040): `viewer` over GraphQL (id, name, role, workspaces),
 * the Supabase session, and sign-in / sign-out. The workspace guard and the top bar read it.
 */
export { useSession, useSignIn, useSignOut, type SignIn } from './api/session';
export { ensureViewer, useViewer, type Viewer } from './api/viewer';
export { NOT_REGISTERED, signInMessage } from './model/messages';
