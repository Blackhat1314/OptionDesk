/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#111111',
          tertiary: '#181818',
          panel: '#141414',
          hover: '#1e1e1e',
          active: '#252525',
        },
        accent: {
          yellow: '#ffcc00',
          orange: '#ff9900',
          cyan: '#00d4ff',
          purple: '#9b59b6',
        },
        market: {
          up: '#00c853',
          down: '#ff1744',
          neutral: '#78909c',
          'up-dim': '#1a3a22',
          'down-dim': '#3a1a1e',
        },
        text: {
          primary: '#f5f5f5',
          secondary: '#a0a0a0',
          muted: '#606060',
          accent: '#ffcc00',
        },
        border: {
          primary: '#2a2a2a',
          secondary: '#1e1e1e',
          accent: '#ffcc00',
        },
        chart: {
          call: '#00c853',
          put: '#ff1744',
          iv: '#00d4ff',
          gex: '#ffcc00',
          vega: '#9b59b6',
          theta: '#ff9900',
        },
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', '"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
        display: ['"IBM Plex Mono"', 'monospace'],
      },
      fontSize: {
        '2xs': '0.625rem',
        xs: '0.7rem',
        sm: '0.75rem',
        base: '0.8rem',
        md: '0.875rem',
        lg: '1rem',
        xl: '1.125rem',
        '2xl': '1.25rem',
      },
      spacing: {
        0.5: '2px',
        1: '4px',
        1.5: '6px',
        2: '8px',
        3: '12px',
        4: '16px',
        5: '20px',
        6: '24px',
      },
      animation: {
        'pulse-fast': 'pulse 0.8s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.2s ease-out',
        'blink': 'blink 1s step-end infinite',
        'scan': 'scan 3s linear infinite',
        'ticker': 'ticker 40s linear infinite',
        'news': 'news 80s linear infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { transform: 'translateY(4px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        blink: { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0' } },
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        ticker: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-33.333%)' },
        },
        news: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      boxShadow: {
        panel: '0 0 0 1px rgba(255, 204, 0, 0.08)',
        'panel-active': '0 0 0 1px rgba(255, 204, 0, 0.3)',
        glow: '0 0 20px rgba(255, 204, 0, 0.15)',
        'glow-up': '0 0 20px rgba(0, 200, 83, 0.2)',
        'glow-down': '0 0 20px rgba(255, 23, 68, 0.2)',
      },
    },
  },
  plugins: [],
}
