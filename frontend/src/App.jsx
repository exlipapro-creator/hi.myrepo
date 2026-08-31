import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import Dashboard from './views/Dashboard.jsx'
import Incidents from './views/Incidents.jsx'
import Events from './views/Events.jsx'
import Projects from './views/Projects.jsx'
import AIGateway from './views/AIGateway.jsx'
import Runbooks from './views/Runbooks.jsx'
import Audit from './views/Audit.jsx'
import Memory from './views/Memory.jsx'

export default function App() {
  return (
    <div className="app">
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
      </nav>
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
