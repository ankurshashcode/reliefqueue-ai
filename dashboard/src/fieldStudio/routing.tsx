import React, { createContext, useContext, useEffect } from 'react';

type RouterContextType = {
  path: string;
  navigate: (to: string | number) => void;
};

const RouterContext = createContext<RouterContextType | null>(null);

export function NativeRouterProvider({ path, navigate, children }: { path: string; navigate: (to: string | number) => void; children: React.ReactNode }) {
  return <RouterContext.Provider value={{ path: String(path || '/field/my-work'), navigate }}>{children}</RouterContext.Provider>;
}

function useRouter() {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error('Native router hook used outside NativeRouterProvider');
  return ctx;
}

export function useNavigate() {
  return useRouter().navigate;
}

export function useLocation() {
  return { pathname: String(useRouter().path || '/field/my-work') };
}

export function useParams() {
  const { path } = useRouter();
  const currentPath = String(path || window.location.pathname || '/field/my-work');
  const caseMatch = currentPath.match(/\/field\/cases\/([^/]+)/);
  return { id: caseMatch ? decodeURIComponent(caseMatch[1]) : undefined };
}

export function Link({ to, className, children, ...rest }: any) {
  const navigate = useNavigate();
  const href = typeof to === 'string' ? to : '#';
  return (
    <a
      {...rest}
      href={href}
      className={className}
      onClick={(event) => {
        if (typeof rest.onClick === 'function') rest.onClick(event);
        if (event.defaultPrevented) return;
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export function NavLink({ to, className, children, ...rest }: any) {
  const { path } = useRouter();
  const currentPath = String(path || window.location.pathname || '/field/my-work');
  const targetPath = typeof to === 'string' ? to : String(to || '');
  const isActive = Boolean(targetPath) && (currentPath === targetPath || (targetPath !== '/field/my-work' && currentPath.startsWith(targetPath)));
  const resolvedClassName = typeof className === 'function' ? className({ isActive }) : className;
  return <Link to={to} className={resolvedClassName} {...rest}>{children}</Link>;
}

export function Navigate({ to, replace }: { to: string | number; replace?: boolean }) {
  const navigate = useNavigate();
  useEffect(() => { navigate(to); }, [navigate, to, replace]);
  return null;
}

export function BrowserRouter({ children }: { children: React.ReactNode }) { return <>{children}</>; }
export function Router({ children }: { children: React.ReactNode }) { return <>{children}</>; }
export function Routes({ children }: { children: React.ReactNode }) { return <>{children}</>; }
export function Route() { return null; }
export function Outlet() { return null; }
