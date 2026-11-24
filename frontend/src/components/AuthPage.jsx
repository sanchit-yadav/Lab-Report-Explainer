import React, { useState } from 'react'
import { Dna, ArrowLeft, ShieldCheck, Eye, EyeOff, Loader2 } from 'lucide-react'

export function AuthPage({ initialMode = 'login', onNavigate, onAuthSuccess, client }) {
  const [isLogin, setIsLogin] = useState(initialMode === 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)

    if (!email || !password) {
      setError('Please provide both an email address and password.')
      return
    }

    if (!isLogin) {
      if (password.length < 8) {
        setError('Password must be at least 8 characters long.')
        return
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match. Please re-enter.')
        return
      }
    }

    setLoading(true)
    try {
      let data
      if (isLogin) {
        data = await client.login(email.trim(), password)
      } else {
        data = await client.register(email.trim(), password, fullName.trim() || null)
      }
      onAuthSuccess(data.user, data.access_token)
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4 sm:p-6 lg:p-8">
      <div className="w-full max-w-4xl bg-white rounded-3xl border border-slate-200/90 shadow-2xl shadow-slate-900/10 overflow-hidden grid lg:grid-cols-12 min-h-[580px]">
        
        {/* Left Pane: Deep Navy Showcase */}
        <div className="lg:col-span-5 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-8 sm:p-10 text-white flex flex-col justify-between border-b lg:border-b-0 lg:border-r border-slate-800">
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-teal-500/10 border border-teal-500/30 text-teal-400 flex items-center justify-center">
                <Dna className="w-5 h-5" />
              </div>
              <span className="font-extrabold text-white tracking-tight text-lg">LabExplainer</span>
            </div>

            <div className="space-y-3">
              <h2 className="text-2xl sm:text-3xl font-black text-white leading-tight">
                {isLogin 
                  ? 'Welcome Back to Clinical Intelligence.' 
                  : 'Transform Complex Reports Into Clear Knowledge.'}
              </h2>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                {isLogin
                  ? 'Sign in to access your persistent laboratory report history, past biomarker evaluations, and physician consultation notes.'
                  : 'Create your free account to upload laboratory reports, track biomarker trends, and generate physician-aligned discussion guides.'}
              </p>
            </div>

            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2.5 text-xs text-slate-200 font-medium">
                <span className="text-emerald-400 font-bold">✓</span> Multi-Tier OCR & Table Geometry Parsing
              </div>
              <div className="flex items-center gap-2.5 text-xs text-slate-200 font-medium">
                <span className="text-emerald-400 font-bold">✓</span> Pure Deterministic Reference Range Flagging
              </div>
              <div className="flex items-center gap-2.5 text-xs text-slate-200 font-medium">
                <span className="text-emerald-400 font-bold">✓</span> Grounded MedlinePlus Clinical Guidelines
              </div>
              <div className="flex items-center gap-2.5 text-xs text-slate-200 font-medium">
                <span className="text-emerald-400 font-bold">✓</span> 100% Local SQLite Data Privacy & Audit Logs
              </div>
            </div>
          </div>

          <div className="pt-6 border-t border-slate-800 text-[11px] text-slate-400 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Zero PHI Logged • Cryptographic Audit Log
          </div>
        </div>

        {/* Right Pane: Form */}
        <div className="lg:col-span-7 p-8 sm:p-12 flex flex-col justify-between">
          <div>
            <button
              onClick={() => onNavigate('landing')}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition mb-6"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Home
            </button>

            <div className="space-y-1 mb-8">
              <h3 className="text-2xl font-black text-slate-900 tracking-tight">
                {isLogin ? 'Sign In to Your Workspace' : 'Create Your Free Account'}
              </h3>
              <p className="text-xs text-slate-500">
                {isLogin 
                  ? 'Enter your verified credentials to access your analysis dashboard.' 
                  : 'Get started with intelligent diagnostic interpretation in seconds.'}
              </p>
            </div>

            {error && (
              <div className="mb-6 p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs font-medium text-rose-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {!isLogin && (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Jane Doe"
                      className="w-full text-xs bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full text-xs bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full text-xs bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 pr-10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {!isLogin && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Confirm Password</label>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full text-xs bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition"
                  />
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 py-3 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 rounded-xl shadow-md transition flex items-center justify-center gap-2 cursor-pointer"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {isLogin ? 'Sign In' : 'Create Free Account'}
              </button>
            </form>
          </div>

          <div className="pt-6 mt-6 border-t border-slate-100 text-center text-xs text-slate-500">
            {isLogin ? "Don't have an account yet?" : 'Already have an account?'}
            <button
              onClick={() => {
                setError(null)
                setEmail('')
                setPassword('')
                setConfirmPassword('')
                setFullName('')
                setIsLogin(!isLogin)
              }}
              className="ml-1.5 font-bold text-slate-900 hover:underline"
            >
              {isLogin ? 'Create Account' : 'Sign In'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
