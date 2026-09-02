import React, { useState } from 'react';
import { ArrowRight, Lock, User, Mail, Shield, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';

export default function Login({ onLoginSuccess }) {
  const [isSignup, setIsSignup] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Client-side validations
    if (!username.trim() || !password) {
      setError('Please fill in all required fields.');
      return;
    }

    if (isSignup) {
      if (password.length < 8) {
        setError('Password must be at least 8 characters long.');
        return;
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        return;
      }
    }

    setLoading(true);
    const endpoint = isSignup ? `${API_BASE}/auth/signup` : `${API_BASE}/auth/login`;
    const payload = isSignup
      ? { username: username.trim(), password, email: email.trim() || undefined }
      : { username: username.trim(), password };

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detailMsg = typeof data.detail === 'string'
          ? data.detail
          : (Array.isArray(data.detail) ? data.detail[0]?.msg : 'Authentication failed.');
        throw new Error(detailMsg || 'Authentication failed.');
      }

      // Store token and trigger callback
      if (data.access_token) {
        localStorage.setItem('sovereignx_token', data.access_token);
        if (onLoginSuccess) {
          onLoginSuccess(data.user, data.access_token);
        }
      }
    } catch (err) {
      setError(err.message || 'An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans flex flex-col justify-between relative overflow-hidden">
      {/* Minimal Top Bar - Ciklum Inspired */}
      <header className="w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between z-20">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 p-[2px] flex items-center justify-center shadow-md">
            <div className="w-full h-full bg-white rounded-full flex items-center justify-center">
              <Shield className="w-5 h-5 text-blue-600" />
            </div>
          </div>
          <span className="font-mono text-xl font-bold tracking-tight text-slate-900">
            Sovereign<span className="text-blue-600">X</span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-slate-500 bg-white/80 backdrop-blur-sm border border-slate-200/80 px-3.5 py-1.5 rounded-full shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>INDUSTRIAL SECURITY GATEWAY</span>
        </div>
      </header>

      {/* Main Content Body */}
      <main className="w-full max-w-7xl mx-auto px-6 my-auto py-8 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center z-20">
        
        {/* Left Column - Ciklum Style Typography & Value Proposition */}
        <div className="lg:col-span-7 space-y-6">
          <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200/60 text-blue-700 px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide">
            <span>AIR-GAPPED ENTERPRISE AI PLATFORM</span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.1] text-slate-900">
            Engineering Precision.{' '}
            <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 bg-clip-text text-transparent">
              AI Ingenuity.
            </span>{' '}
            Experience Reimagined.
          </h1>

          <p className="text-base md:text-lg text-slate-600 leading-relaxed max-w-xl">
            Reshaping industrial operations and critical infrastructure, powered by world-class, 
            deterministic RAG & autonomous agent verification.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4">
            <div className="flex items-start gap-3 p-4 rounded-2xl bg-white/70 border border-slate-200/70 shadow-sm backdrop-blur-sm">
              <CheckCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-slate-900 uppercase font-mono tracking-wider">Zero External Data Leakage</h4>
                <p className="text-xs text-slate-500 mt-1">Fully self-hosted BGE-M3 and local LLM execution.</p>
              </div>
            </div>

            <div className="flex items-start gap-3 p-4 rounded-2xl bg-white/70 border border-slate-200/70 shadow-sm backdrop-blur-sm">
              <CheckCircle className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-slate-900 uppercase font-mono tracking-wider">Strict SOP Limit Audit</h4>
                <p className="text-xs text-slate-500 mt-1">Deterministic calculation verifier & tool execution.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column - Ciklum Style Glowing Ambient Blob & Card */}
        <div className="lg:col-span-5 relative flex items-center justify-center">
          
          {/* Soft Colored Glowing Blurred Ambient Blob Behind Login Card */}
          <div className="absolute -inset-4 bg-gradient-to-r from-cyan-400 via-blue-500 to-indigo-500 rounded-full blur-3xl opacity-30 animate-pulse pointer-events-none" />

          {/* Form Card */}
          <div className="w-full bg-white/90 backdrop-blur-md border border-slate-200/80 rounded-3xl p-8 shadow-2xl space-y-6 relative z-10">
            <div className="space-y-1 text-center">
              <h2 className="text-2xl font-bold tracking-tight text-slate-900">
                {isSignup ? 'Create Account' : 'Welcome Back'}
              </h2>
              <p className="text-xs text-slate-500">
                {isSignup 
                  ? 'Join your engineering team on SovereignX'
                  : 'Enter your credentials to access the console'}
              </p>
            </div>

            {error && (
              <div className="p-3.5 rounded-2xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Username Field */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 font-mono tracking-wider uppercase ml-1">
                  Username
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="e.g. j.smith"
                    className="w-full bg-slate-50 border border-slate-200 rounded-full pl-11 pr-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/40 focus:border-blue-600 transition-all"
                  />
                </div>
              </div>

              {/* Optional Email Field for Signup */}
              {isSignup && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 font-mono tracking-wider uppercase ml-1">
                    Email <span className="text-slate-400 text-[10px] font-sans font-normal">(Optional)</span>
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="e.g. j.smith@company.com"
                      className="w-full bg-slate-50 border border-slate-200 rounded-full pl-11 pr-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/40 focus:border-blue-600 transition-all"
                    />
                  </div>
                </div>
              )}

              {/* Password Field */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 font-mono tracking-wider uppercase ml-1">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={isSignup ? 'At least 8 characters' : 'Enter password'}
                    className="w-full bg-slate-50 border border-slate-200 rounded-full pl-11 pr-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/40 focus:border-blue-600 transition-all"
                  />
                </div>
              </div>

              {/* Confirm Password Field for Signup */}
              {isSignup && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 font-mono tracking-wider uppercase ml-1">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                    <input
                      type="password"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Re-enter password"
                      className="w-full bg-slate-50 border border-slate-200 rounded-full pl-11 pr-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/40 focus:border-blue-600 transition-all"
                    />
                  </div>
                </div>
              )}

              {/* Submit Pill Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-full shadow-lg hover:shadow-blue-500/25 transition-all flex items-center justify-center gap-2 group disabled:opacity-50 mt-2"
              >
                {loading ? (
                  <RefreshCw className="w-4 h-4 animate-spin text-white" />
                ) : (
                  <>
                    <span>{isSignup ? 'Create Account & Log In' : 'Sign In to Console'}</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </>
                )}
              </button>
            </form>

            {/* Mode Switch Toggle Link */}
            <div className="pt-2 text-center border-t border-slate-100">
              <button
                type="button"
                onClick={() => {
                  setIsSignup(!isSignup);
                  setError(null);
                }}
                className="text-xs text-slate-600 hover:text-blue-600 font-medium transition-colors"
              >
                {isSignup ? (
                  <>Already have an account? <span className="text-blue-600 font-semibold underline">Log in</span></>
                ) : (
                  <>Don't have an account? <span className="text-blue-600 font-semibold underline">Sign up</span></>
                )}
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full max-w-7xl mx-auto px-6 py-4 text-center text-xs font-mono text-slate-400 z-20">
        © 2026 SovereignX Industrial Intelligence Platform. All operations local & secure.
      </footer>
    </div>
  );
}
