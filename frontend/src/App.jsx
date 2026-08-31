import { useState, useEffect } from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import Auth from './views/Auth.jsx'
import Dashboard from './views/Dashboard.jsx'
import Incidents from './views/Incidents.jsx'
import Events from './views/Events.jsx'
import Projects from './views/Projects.jsx'
import AIGateway from './views/AIGateway.jsx'
import Runbooks from './views/Runbooks.jsx'
import Audit from './views/Audit.jsx'
import Memory from './views/Memory.jsx'

function Sidebar({ onLogout }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        hi.myrepo
        <span>COMMAND CENTER</span>
      </div>
      <div className="sidebar-nav">
        <NavLink to="/dashboard" end>📊 Dashboard</NavLink>
        <NavLink to="/incidents">🔥 Incidents</NavLink>
        <NavLink to="/events">📡 Events</NavLink>
        <NavLink to="/projects">📦 Projects</NavLink>
        <NavLink to="/ai-gateway">🤖 AI Gateway</NavLink>
        <NavLink to="/runbooks">📋 Runbooks</NavLink>
        <NavLink to="/memory">🧠 Memory</NavLink>
        <NavLink to="/audit">📝 Audit</NavLink>
      </div>
      <div style={{ marginTop: 'auto', paddingTop: 'var(--space-lg)' }}>
        <button
          onClick={onLogout}
          className="btn"
          style={{ width: '100%', justifyContent: 'center', fontSize: '12px', color: 'var(--text-muted)' }}
        >
          ↩ Logout
        </button>
      </div>
    </nav>
  )
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token'))

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
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
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
      <Sidebar onLogout={handleLogout} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/incidents" element={<Incidents />} />
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
