import { ChevronDown, PanelsTopLeft } from 'lucide-react';

type ProductRole = 'command' | 'field' | 'local';

const ROLES: Array<{ id: ProductRole; label: string; href: string; description: string }> = [
  { id: 'command', label: 'Command Center', href: '/dashboard?source=latest', description: 'Runtime coordination and oversight' },
  { id: 'field', label: 'Field Coordinator', href: '/field/my-work', description: 'Mobile case and outbox workflow' },
  { id: 'local', label: 'Local Coordinator', href: '/local-coordinator?source=latest', description: 'Scenario and local operations context' },
];

export function ProductRoleSwitcher({
  currentRole,
  dark = false,
  compact = false,
}: {
  currentRole: ProductRole;
  dark?: boolean;
  compact?: boolean;
}) {
  const current = ROLES.find((role) => role.id === currentRole) || ROLES[0];
  const summaryClass = dark
    ? 'border-slate-600 bg-slate-800 text-white hover:bg-slate-700'
    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50';
  const menuClass = dark
    ? 'border-slate-700 bg-slate-900 text-white'
    : 'border-slate-200 bg-white text-slate-900';

  return (
    <details className="group relative shrink-0">
      <summary
        aria-label="Switch ReliefQueue workspace"
        className={`list-none cursor-pointer select-none rounded-lg border px-2 py-2 text-xs font-bold shadow-sm transition-colors sm:px-3 ${summaryClass}`}
      >
        <span className="inline-flex items-center gap-2">
          {compact && <PanelsTopLeft className="h-4 w-4 shrink-0" aria-hidden="true" />}
          <span className={compact ? 'hidden sm:inline' : undefined}>
            {compact ? current.label.replace(' Coordinator', '') : current.label}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
        </span>
      </summary>
      <nav
        aria-label="ReliefQueue workspaces"
        className={`absolute right-0 z-[120] mt-2 w-72 overflow-hidden rounded-xl border shadow-2xl ${menuClass}`}
      >
        {ROLES.map((role) => {
          const active = role.id === currentRole;
          return (
            <a
              key={role.id}
              href={role.href}
              aria-current={active ? 'page' : undefined}
              className={`block border-b px-4 py-3 last:border-b-0 ${
                dark ? 'border-slate-700 hover:bg-slate-800' : 'border-slate-100 hover:bg-slate-50'
              } ${active ? (dark ? 'bg-slate-800' : 'bg-blue-50') : ''}`}
            >
              <span className="block text-sm font-bold">{role.label}</span>
              <span className={`mt-1 block text-xs ${dark ? 'text-slate-400' : 'text-slate-500'}`}>{role.description}</span>
            </a>
          );
        })}
      </nav>
    </details>
  );
}
