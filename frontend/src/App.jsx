import { useState, useEffect } from 'react'
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import { Menu, X, LayoutDashboard, AlertTriangle, Radio, Package, Bot, BookOpen, Brain, FileText, LogOut } from 'lucide-react'
import { apiUrl } from './utils/api.js'
import Auth from './views/Auth.jsx'
import Dashboard from './views/Dashboard.jsx'
import Incidents from './views/Incidents.jsx'
import IncidentDetail from './views/IncidentDetail.jsx'
import Events from './views/Events.jsx'
import Projects from './views/Projects.jsx'
import AIGateway from './views/AIGateway.jsx'
import Runbooks from './views/Runbooks.jsx'
import Audit from './views/Audit.jsx'
import Memory from './views/Memory.jsx'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/incidents', icon: AlertTriangle, label: 'Incidents' },
  { to: '/events', icon: Radio, label: 'Events' },
  { to: '/projects', icon: Package, label: 'Projects' },
  { to: '/ai-gateway', icon: Bot, label: 'AI Gateway' },
  { to: '/runbooks', icon: BookOpen, label: 'Runbooks' },
  { to: '/memory', icon: Brain, label: 'Memory' },
  { to: '/audit', icon: FileText, label: 'Audit' },
]

function Sidebar({ onLogout }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        hi.myrepo
        <span>COMMAND CENTER</span>
      </div>
      <div className="sidebar-nav">
        {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
          <NavLink key={to} to={to} end={end}>
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </div>
      <div style={{ marginTop: 'auto', paddingTop: 'var(--space-lg)' }}>
        <button
          onClick={onLogout}
          className="btn"
          style={{ width: '100%', justifyContent: 'center', fontSize: '12px', color: 'var(--text-muted)' }}
        >
          <LogOut size={14} /> Logout
        </button>
      </div>
    </nav>
  )
}

function MobileDrawer({ onLogout, isOpen, onClose }) {
  return (
    <>
      <div className={`drawer-overlay ${isOpen ? 'visible' : ''}`} onClick={onClose} />
      <div className={`drawer ${isOpen ? 'open' : ''}`}>
        {/* Header */}
        <div className="drawer-header">
          <div className="drawer-brand">
            <span className="drawer-brand-name">hi.myrepo</span>
            <span className="drawer-brand-sub">CONTROL PLANE</span>
          </div>
          <button
            className="drawer-close"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="drawer-nav">
          {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
            <NavLink key={to} to={to} end={end} className="drawer-nav-item" onClick={onClose}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Bottom action */}
        <div className="drawer-footer">
          <button onClick={onLogout} className="drawer-nav-item drawer-logout">
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </div>
    </>
  )
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token'))
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  // Close sidebar on Escape key
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && sidebarOpen) {
        setSidebarOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [sidebarOpen])

  function handleLogin(newToken) {
    setToken(newToken)
  }

  function handleLogout() {
    localStorage.removeItem('token')
    setToken(null)
  }

  // Validate token on mount
  useEffect(() => {
    if (!token) return
    fetch(apiUrl('/api/v1/auth/me'), { headers: { Authorization: `Bearer ${token}` } })
      .then(res => {
        if (!res.ok) {
          localStorage.removeItem('token')
          setToken(null)
        }
      })
      .catch(() => {
        // Backend unreachable — keep token, let views handle errors
      })
  }, [token])

  if (!token) {
    return <Auth onLogin={handleLogin} />
  }

  return (
    <div className="app">
      {/* Mobile header */}
      <div className="mobile-header">
        <span className="mobile-header-logo">hi.myrepo</span>
        <button className="hamburger-btn" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle navigation">
          {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>
      <Sidebar onLogout={handleLogout} />
      <MobileDrawer onLogout={handleLogout} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          <Route path="/events" element={<Events />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/ai-gateway" element={<AIGateway />} />
          <Route path="/runbooks" element={<Runbooks />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/audit" element={<Audit />} />
        </Routes>
      </main>
    </div>
  )
}
