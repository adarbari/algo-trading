/**
 * The people's columns: one declared user per row, in declaration order. The phone shows the
 * person and the role.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import {
  licencesText,
  roleLabel,
  TERM_OF_LICENCES,
  TERM_OF_PERSON,
  TERM_OF_ROLE,
  type Person,
} from '@/entities/user-registry';
import { termHelp } from '@/features/guide-help';

export function personColumns(): DataTableColumn<Person>[] {
  return [
    {
      id: 'person',
      header: 'Person',
      value: (p) => p.id,
      hideable: false,
      grow: true,
      essential: true,
      headerAction: termHelp(TERM_OF_PERSON),
      cell: ({ row }) => (
        <>
          <Mono size="sm">{row.id}</Mono> {row.name}
        </>
      ),
    },
    {
      id: 'role',
      header: 'Role',
      value: (p) => p.role,
      essential: true,
      headerAction: termHelp(TERM_OF_ROLE),
      cell: ({ row }) => (
        <StatusBadge tone={row.role === 'admin' ? 'info' : 'neutral'}>
          {roleLabel(row.role)}
        </StatusBadge>
      ),
    },
    {
      id: 'licences',
      header: 'Licences held',
      value: (p) => licencesText(p),
      headerAction: termHelp(TERM_OF_LICENCES),
      mono: true,
    },
  ];
}
