import { NavLink } from '../routing';
import { CircleHelp, ClipboardList, Home, Send } from 'lucide-react';
import { cn } from '../lib/utils';

export const FieldBottomNav = () => {
  const navItems = [
    { label: 'My Work', path: '/field/my-work', icon: Home },
    { label: 'My Cases', path: '/field/my-cases', icon: ClipboardList },
    { label: 'Outbox', path: '/field/outbox', icon: Send },
    { label: 'Help', path: '/field/help', icon: CircleHelp },
  ];

  return (
    <nav
      aria-label="Field Coordinator navigation"
      className="fixed bottom-0 left-0 right-0 z-50 mx-auto flex h-16 w-full max-w-xl items-center justify-around border-t border-outline-variant bg-surface px-2 pb-safe shadow-[0_-8px_24px_rgba(15,23,42,0.08)] md:rounded-t-2xl md:border-x"
    >
      {navItems.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) => cn(
            'flex min-w-16 flex-col items-center justify-center rounded-xl px-2 py-1 transition-transform active:scale-95',
            isActive ? 'bg-primary-container text-on-primary-container' : 'text-on-surface-variant hover:bg-surface-container-low'
          )}
        >
          <item.icon size={20} />
          <span className="mt-1 text-[11px] font-semibold sm:text-xs">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
};
