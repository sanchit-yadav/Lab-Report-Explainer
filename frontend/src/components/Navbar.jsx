import React from 'react'
import { Dna, UserPlus, LogOut, LayoutDashboard } from 'lucide-react'

export function Navbar({ view, onNavigate, user, onLogout, backendOnline }) {
  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-white/90 border-b border-slate-200/80 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand Logo */}
        <div 
          onClick={() => onNavigate(user ? 'dashboard' : 'landing')}
          className="flex items-center gap-3 cursor-pointer select-none group"
        >
          <div className="w-10 h-10 rounded-xl bg-slate-900 text-teal-400 flex items-center justify-center shadow-md shadow-slate-900/10 group-hover:bg-slate-800 transition">
            <Dna className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-slate-900 tracking-tight text-lg">LabExplainer</span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200">
                Clinical CDS
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-medium hidden sm:block">AI Clinical Lab Report Explainer</p>
          </div>
        </div>

        {/* Center Nav Links (Visible when on landing page) */}
        {view === 'landing' && (
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
            <a href="#how-it-works" className="hover:text-slate-900 transition">How It Works</a>
            <a href="#features" className="hover:text-slate-900 transition">Features</a>
            <a href="#safety" className="hover:text-slate-900 transition">Safety & Trust</a>
            <a href="#faq" className="hover:text-slate-900 transition">FAQ</a>
          </nav>
        )}

        {/* Right Actions */}
        <div className="flex items-center gap-3">
          {/* Backend Health indicator */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border bg-slate-50">
            <span className={`w-2 h-2 rounded-full ${backendOnline ? 'bg-emerald-500 animate-ping' : 'bg-amber-500'}`} />
            <span className={backendOnline ? 'text-emerald-700' : 'text-amber-700'}>
              {backendOnline ? 'API Connected' : 'API Offline'}
            </span>
          </div>

          {user ? (
            <div className="flex items-center gap-3">
              <button
                onClick={() => onNavigate('dashboard')}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                  view === 'dashboard'
                    ? 'bg-slate-100 text-slate-900 font-bold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <LayoutDashboard className="w-4 h-4" />
                Workspace
              </button>

              <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                <div className="text-right hidden sm:block">
                  <div className="text-xs font-bold text-slate-900">{user.full_name || user.email}</div>
                  <div className="text-[10px] uppercase font-semibold text-teal-600">Patient</div>
                </div>
                <button
                  onClick={onLogout}
                  title="Sign Out"
                  className="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => onNavigate('login')}
                className="px-3.5 py-2 text-xs font-semibold text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition"
              >
                Sign In
              </button>
              <button
                onClick={() => onNavigate('register')}
                className="px-4 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg shadow-sm transition flex items-center gap-1.5"
              >
                <UserPlus className="w-3.5 h-3.5" />
                Get Started
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
