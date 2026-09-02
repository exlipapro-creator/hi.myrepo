import { useState } from 'react'
import { apiUrl } from '../utils/api.js'

const API = apiUrl('/api/v1')

export default function Auth({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      let res
      if (mode === 'login') {
        res = await fetch(`${API}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
      } else {
        res = await fetch(`${API}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password,
            full_name: fullName,
            organization_name: orgName,
          }),
        })
      }

      const data = await res.json()

      if (!res.ok) {
        setError(data.detail || 'Authentication failed')
        return
      }

      localStorage.setItem('token', data.access_token)
      onLogin(data.access_token)
    } catch (err) {
      setError('Connection failed — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: 'var(--bg-primary)',
    }}>
      <div style={{
        width: '380px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-xl)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-xl)' }}>
          <div style={{
            fontSize: '20px',
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            color: 'var(--accent-blue)',
            marginBottom: '4px',
          }}>
            hi.myrepo
          </div>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}>
            COMMAND CENTER
          </div>
        </div>

        {/* Tab toggle */}
        <div style={{
          display: 'flex',
          gap: '2px',
          background: 'var(--bg-secondary)',
          borderRadius: 'var(--radius-sm)',
          padding: '3px',
          marginBottom: 'var(--space-lg)',
        }}>
          <button
            onClick={() => { setMode('login'); setError('') }}
            style={{
              flex: 1,
              padding: '6px',
              border: 'none',
              borderRadius: '4px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              background: mode === 'login' ? 'var(--accent-blue)' : 'transparent',
              color: mode === 'login' ? 'white' : 'var(--text-secondary)',
              transition: 'all 0.15s',
            }}
          >
            Login
          </button>
          <button
            onClick={() => { setMode('register'); setError('') }}
            style={{
              flex: 1,
              padding: '6px',
              border: 'none',
              borderRadius: '4px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              background: mode === 'register' ? 'var(--accent-blue)' : 'transparent',
              color: mode === 'register' ? 'white' : 'var(--text-secondary)',
              transition: 'all 0.15s',
            }}
          >
            Register
          </button>
        </div>

        {error && (
          <div style={{
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: 'var(--accent-red)',
            fontSize: '13px',
            marginBottom: 'var(--space-md)',
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 'var(--space-md)' }}>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              style={{
                width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
                fontSize: '13px', outline: 'none',
              }}
            />
          </div>

          <div style={{ marginBottom: 'var(--space-md)' }}>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Password
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="min 8 characters"
              style={{
                width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
                fontSize: '13px', outline: 'none',
              }}
            />
          </div>

          {mode === 'register' && (
            <>
              <div style={{ marginBottom: 'var(--space-md)' }}>
                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                  placeholder="Jane Doe"
                  style={{
                    width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
                    fontSize: '13px', outline: 'none',
                  }}
                />
              </div>
              <div style={{ marginBottom: 'var(--space-md)' }}>
                <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Organization
                </label>
                <input
                  type="text"
                  required
                  value={orgName}
                  onChange={e => setOrgName(e.target.value)}
                  placeholder="My Team"
                  style={{
                    width: '100%', background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)',
                    fontSize: '13px', outline: 'none',
                  }}
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{
              width: '100%',
              justifyContent: 'center',
              padding: '8px',
              marginTop: 'var(--space-sm)',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Please wait...' : mode === 'login' ? 'Login' : 'Create Account'}
          </button>
        </form>
      </div>
    </div>
  )
}
