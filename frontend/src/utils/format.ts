export const fmt = {
  /** Format a number with commas: 24,123.45 */
  num: (n: number, decimals = 2): string => {
    if (n === undefined || n === null || isNaN(n)) return '—';
    return n.toLocaleString('en-IN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  },

  /** Format large numbers: 1.2M, 45.3K */
  compact: (n: number): string => {
    if (!n) return '—';
    if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`;
    if (Math.abs(n) >= 1e5) return `${(n / 1e5).toFixed(2)}L`;
    if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return n.toFixed(0);
  },

  /** Format as percentage: 12.34% */
  pct: (n: number, decimals = 2): string => {
    if (n === undefined || n === null || isNaN(n)) return '—';
    return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`;
  },

  /** Format IV: 23.45% */
  iv: (n: number): string => {
    if (!n) return '—';
    return `${n.toFixed(2)}%`;
  },

  /** Format Greeks with appropriate decimals */
  delta: (n: number): string => n.toFixed(4),
  gamma: (n: number): string => n.toFixed(5),
  theta: (n: number): string => n.toFixed(4),
  vega: (n: number): string => n.toFixed(4),

  /** Format price with 2 decimals */
  price: (n: number): string => {
    if (!n) return '—';
    return n.toFixed(2);
  },

  /** Format OI change with sign */
  oiChange: (n: number): string => {
    if (!n) return '—';
    const sign = n > 0 ? '+' : '';
    return `${sign}${fmt.compact(n)}`;
  },

  /** Color class based on value sign */
  colorClass: (n: number, options?: { inverse?: boolean }): string => {
    if (n === 0) return 'text-text-secondary';
    const positive = options?.inverse ? n < 0 : n > 0;
    return positive ? 'text-market-up' : 'text-market-down';
  },

  /** Format timestamp to HH:MM:SS IST */
  time: (ts: number): string => {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
    });
  },

  /** Format date */
  date: (dateStr: string): string => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  },

  /** Strike strike to display format */
  strike: (n: number): string => {
    return n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  },
};

export function clamp(val: number, min: number, max: number): number {
  return Math.min(Math.max(val, min), max);
}

export function getOIBarWidth(oi: number, maxOI: number): number {
  if (!maxOI) return 0;
  return clamp((oi / maxOI) * 100, 0, 100);
}

export function getITMClass(strike: number, spot: number, optionType: 'CE' | 'PE'): string {
  const isITM = optionType === 'CE' ? strike <= spot : strike >= spot;
  return isITM ? 'bg-bg-tertiary' : '';
}
