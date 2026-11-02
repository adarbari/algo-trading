/** The user-registry entity's types, as the operation selects them. */
import type { gqlTypes } from '@/shared/api';

export type UserRegistry = NonNullable<gqlTypes.UserRegistryQuery['userRegistry']>;
export type Person = UserRegistry['people'][number];
