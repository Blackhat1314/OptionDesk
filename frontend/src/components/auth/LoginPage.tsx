import React, { useState } from 'react';
import { authApi, tokenStore } from '../../utils/api';

// Demo mode token — special value that switches all API calls to /api/demo/*
export const DEMO_TOKEN = 'DEMO_MODE_TOKEN';

interface Props {
  onAuth: () => void;
}

export const LoginPage: React.FC<Props> = ({ onAuth }) => {
  const [username, setUsername]   = useState('');
  const [password, setPassword]   = useState('');
  const [error, setError]         = useState('');
  const [loading, setLoading]     = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await authApi.login(username.trim(), password);
      tokenStore.set(result.access_token);
      tokenStore.setUsername(result.username);
      onAuth();
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = async () => {
    setDemoLoading(true);
    // Small delay for UX feel
    await new Promise(r => setTimeout(r, 600));
    tokenStore.set(DEMO_TOKEN);
    tokenStore.setUsername('demo');
    setDemoLoading(false);
    onAuth();
  };

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-4">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: 'linear-gradient(#ffcc00 1px, transparent 1px), linear-gradient(90deg, #ffcc00 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-8 h-8 border-2 border-accent-yellow flex items-center justify-center">
            <div className="w-4 h-4 bg-accent-yellow" />
          </div>
          <div>
            <div className="font-mono text-accent-yellow font-bold text-xl tracking-widest">
              OPTIONS<span className="text-text-secondary">DESK</span>
            </div>
            <div className="font-mono text-text-muted text-2xs tracking-widest">
              BLOOMBERG-GRADE ANALYTICS
            </div>
          </div>
        </div>

        {/* Login Card */}
        <div className="border border-border-primary bg-bg-panel p-6">
          <div className="text-xs font-mono font-bold text-accent-yellow tracking-widest mb-5 text-center">
            LOGIN
          </div>

          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <div>
              <label className="text-2xs font-mono text-text-muted block mb-1 tracking-widest">
                USERNAME
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                autoComplete="username"
                placeholder="your_username"
                className="w-full bg-bg-primary border border-border-primary text-text-primary font-mono text-sm px-3 py-2 focus:outline-none focus:border-accent-yellow placeholder-text-muted/40"
              />
            </div>

            <div>
              <label className="text-2xs font-mono text-text-muted block mb-1 tracking-widest">
                PASSWORD
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
                className="w-full bg-bg-primary border border-border-primary text-text-primary font-mono text-sm px-3 py-2 focus:outline-none focus:border-accent-yellow placeholder-text-muted/40"
              />
            </div>

            {error && (
              <div className="border border-market-down/30 bg-market-down/10 px-3 py-2 text-xs font-mono text-market-down">
                ⚠ {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="py-2.5 bg-accent-yellow text-black font-mono font-bold text-sm tracking-widest hover:bg-yellow-400 disabled:opacity-50 transition-colors mt-1"
            >
              {loading ? '■ AUTHENTICATING...' : '▶ LOGIN'}
            </button>
          </form>

          <div className="mt-4 pt-4 border-t border-border-secondary">
            <p className="text-2xs font-mono text-text-muted text-center">
              Single-device session. Logging in here will sign out other devices.
            </p>
          </div>
        </div>

        {/* Demo Mode Card */}
        <div className="mt-3 border border-border-primary bg-bg-panel/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full bg-accent-yellow animate-pulse" />
            <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">
              DEMO MODE
            </span>
          </div>
          <p className="text-2xs font-mono text-text-muted mb-3">
            Explore the full platform with live market snapshot data. No account needed.
          </p>
          <button
            onClick={handleDemo}
            disabled={demoLoading}
            className="w-full py-2 font-mono font-bold text-xs tracking-widest transition-all border"
            style={{
              color: demoLoading ? '#606060' : '#ffcc00',
              borderColor: demoLoading ? '#2a2a2a' : '#ffcc0040',
              backgroundColor: demoLoading ? 'transparent' : 'rgba(255,204,0,0.05)',
            }}
          >
            {demoLoading ? '■ LOADING DEMO...' : '▶ EXPLORE DEMO'}
          </button>
        </div>

        <p className="text-center text-2xs font-mono text-border-primary mt-4 tracking-widest">
          OPTIONSDESK v2.0 · PRIVATE ACCESS
        </p>
      </div>
    </div>
  );
};
