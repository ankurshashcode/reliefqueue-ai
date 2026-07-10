import { NavLink } from '../routing';
import { ClipboardList, Users, Map, Settings } from 'lucide-react';
import { cn } from '../lib/utils';
import { useAppContext } from '../contexts/AppContext';

export const FieldBottomNav = () => {
  const { showToast } = useAppContext();

  const navItems = [
    { label: 'Cases', path: '/field/my-cases', icon: ClipboardList },
    { label: 'Volunteers', path: '#', icon: Users, disabled: true },
    { label: 'Hub', path: '/field/my-work', icon: Map },
    { label: 'Settings', path: '/field/help', icon: Settings },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 w-full z-50 flex justify-around items-center h-16 px-4 bg-surface border-t border-outline-variant pb-safe">
      {navItems.map((item, idx) => (
        <NavLink
          key={idx}
          to={item.disabled ? '#' : item.path}
          onClick={(e) => {
            if (item.disabled) {
              e.preventDefault();
              showToast('Volunteer view is not active in this prototype.');
            }
          }}
          className={({ isActive }) => cn(
            "flex flex-col items-center justify-center w-16 py-1 rounded-xl transition-transform active:scale-95",
            (isActive && !item.disabled) ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant hover:bg-surface-container-low"
          )}
        >
          <item.icon size={20} className={item.disabled ? "opacity-50" : ""} />
          <span className="font-semibold text-[12px] mt-1">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
};
