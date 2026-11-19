import React, { useState, useEffect } from 'react'
import { api } from './api'
import { Navbar } from './components/Navbar'
import { LandingPage } from './components/LandingPage'
import { AuthPage } from './components/AuthPage'
import { Dashboard } from './components/Dashboard'

export default function App() {
  const [view, setView] = useState('landing') // 'landing' | 'login' | 'register' | 'dashboard'
  const [user, setUser] = useState(null)
  const [backendOnline, setBackendOnline] = useState(false)
  const [loadingInitial, setLoadingInitial] = useState(true)

  // Initial authentication & health check
  useEffect(() => {
    const initApp = async () => {
      // Restore saved session first — don't block on backend health check
      const token = localStorage.getItem('access_token')
      if (token) {
        try {
          const profile = await api.getMe()
          setUser(profile)
          setView('dashboard')
        } catch {
          api.logout()
          setUser(null)
        }
      }
      setLoadingInitial(false)

      // Health check runs after session is restored (non-blocking)
      api.checkHealth().then(setBackendOnline).catch(() => setBackendOnline(false))
    }

    initApp()
  }, [])

  const handleNavigate = (targetView) => {
    setView(targetView)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleAuthSuccess = (userData, token) => {
    setUser(userData)
    setView('dashboard')
  }

  const handleLogout = () => {
    api.logout()
    setUser(null)
    setView('landing')
  }

  if (loadingInitial) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-slate-900 border-t-transparent animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Navbar
        view={view}
        onNavigate={handleNavigate}
        user={user}
        onLogout={handleLogout}
        backendOnline={backendOnline}
      />

      <main className="flex-1">
        {view === 'landing' && <LandingPage onNavigate={handleNavigate} />}
        
        {view === 'login' && (
          <AuthPage
            initialMode="login"
            onNavigate={handleNavigate}
            onAuthSuccess={handleAuthSuccess}
            client={api}
          />
        )}

        {view === 'register' && (
          <AuthPage
            initialMode="register"
            onNavigate={handleNavigate}
            onAuthSuccess={handleAuthSuccess}
            client={api}
          />
        )}

        {view === 'dashboard' && (
          user ? (
            <Dashboard
              user={user}
              client={api}
              onLogout={handleLogout}
            />
          ) : (
            <AuthPage
              initialMode="login"
              onNavigate={handleNavigate}
              onAuthSuccess={handleAuthSuccess}
              client={api}
            />
          )
        )}
      </main>
    </div>
  )
}
