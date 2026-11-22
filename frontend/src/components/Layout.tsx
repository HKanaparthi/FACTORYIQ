import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Cpu,
  Search,
  Database,
  ClipboardCheck,
  BarChart2,
  Zap,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/',             icon: LayoutDashboard, label: 'Operations' },
  { to: '/equipment',    icon: Cpu,             label: 'Equipment' },
  { to: '/investigate',  icon: Search,          label: 'Investigate' },
  { to: '/evidence',     icon: Database,        label: 'Evidence' },
  { to: '/review',       icon: ClipboardCheck,  label: 'Review' },
  { to: '/evaluation',   icon: BarChart2,       label: 'Evaluation' },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      {/* Sidebar */}
      <aside className="flex w-56 flex-shrink-0 flex-col border-r border-slate-800 bg-slate-900">
        {/* Logo */}
        <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-4">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-amber-500/20">
            <Zap className="h-4 w-4 text-amber-400" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-100">FactoryIQ</div>
            <div className="text-xs text-slate-500">Industrial AI</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 p-2 pt-3">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const active =
              to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex items-center gap-2.5 rounded px-3 py-2 text-sm transition-colors ${
                  active
                    ? 'bg-amber-500/10 text-amber-400'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                {label}
              </NavLink>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-slate-800 px-4 py-3">
          <div className="text-xs text-slate-600">Milestone 4 · Simulated Data</div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
