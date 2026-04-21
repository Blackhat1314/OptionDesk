import React, { useState, useEffect, useRef } from 'react';

interface Stream {
  id: string;
  name: string;
  liveUrl: string;
  videoId: string | null;
  embedUrl: string | null;
  isLive: boolean;
}

const CHANNEL_META: Record<string, { description: string; color: string }> = {
  cnbctv18:         { description: "India's #1 business news",     color: '#0066cc' },
  etnow:            { description: 'Economic Times markets',        color: '#ff6600' },
  zeebusiness:      { description: 'Hindi business & markets',      color: '#cc0000' },
  ndtvprofit:       { description: 'NDTV business & markets',       color: '#009933' },
  bloomberg:        { description: 'Bloomberg global markets',      color: '#cc6600' },
  moneycontrol:     { description: 'Moneycontrol live',             color: '#003399' },
  moneycontrolhindi:{ description: 'Moneycontrol Hindi',            color: '#6600cc' },
};

export const LiveTVTab: React.FC = () => {
  const [streams, setStreams] = useState<Stream[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<string>('cnbctv18');
  const iframeKey = useRef(0);

  const fetchStreams = async () => {
    try {
      const res = await fetch('/api/livetv/streams');
      const data = await res.json();
      if (data.streams?.length) {
        setStreams(data.streams);
        // Auto-select first live channel
        const firstLive = data.streams.find((s: Stream) => s.isLive);
        if (firstLive) setActiveId(firstLive.id);
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    fetchStreams();
    // Refresh video IDs every 10 minutes (streams change IDs rarely)
    const t = setInterval(fetchStreams, 600_000);
    return () => clearInterval(t);
  }, []);

  const active = streams.find(s => s.id === activeId) ?? streams[0];
  const meta = active ? CHANNEL_META[active.id] : null;

  const handleChannelChange = (id: string) => {
    iframeKey.current += 1;
    setActiveId(id);
  };

  // Refresh just this channel's video ID
  const refreshChannel = async (id: string) => {
    try {
      const res = await fetch(`/api/livetv/stream/${id}`);
      const data = await res.json();
      setStreams(prev => prev.map(s => s.id === id ? { ...s, ...data } : s));
      iframeKey.current += 1;
    } catch {}
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg-primary">
      {/* Sidebar */}
      <div className="w-52 shrink-0 border-r border-border-primary flex flex-col bg-bg-secondary">
        <div className="px-3 py-2 border-b border-border-primary flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-market-up animate-pulse" />
          <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">LIVE TV</span>
          {loading && <span className="text-2xs text-text-muted font-mono ml-auto animate-pulse">loading...</span>}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            // Skeleton placeholders
            Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="px-3 py-2.5 border-b border-border-secondary">
                <div className="h-3 bg-bg-hover rounded w-24 mb-1 animate-pulse" />
                <div className="h-2 bg-bg-hover rounded w-32 animate-pulse" />
              </div>
            ))
          ) : (
            streams.map(s => {
              const m = CHANNEL_META[s.id];
              const isActive = s.id === activeId;
              return (
                <button key={s.id} onClick={() => handleChannelChange(s.id)}
                  className={`w-full text-left px-3 py-2.5 border-b border-border-secondary transition-all ${
                    isActive ? 'bg-accent-yellow/10 border-l-2 border-l-accent-yellow' : 'hover:bg-bg-hover'
                  }`}>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-sm shrink-0"
                      style={{ backgroundColor: isActive ? (m?.color ?? '#888') : '#333' }} />
                    <span className={`text-xs font-mono font-bold ${isActive ? 'text-text-primary' : 'text-text-muted'}`}>
                      {s.name}
                    </span>
                    {/* Live indicator */}
                    {s.isLive
                      ? <span className="ml-auto text-2xs font-mono text-market-up">● LIVE</span>
                      : <span className="ml-auto text-2xs font-mono text-text-muted">offline</span>
                    }
                  </div>
                  <div className="text-2xs text-text-muted mt-0.5 pl-4 leading-tight">{m?.description}</div>
                </button>
              );
            })
          )}
        </div>

        <div className="px-3 py-2 border-t border-border-primary">
          <div className="text-2xs text-text-muted font-mono leading-tight">
            Video IDs auto-resolved via YouTube oEmbed
          </div>
        </div>
      </div>

      {/* Player */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-border-primary bg-bg-panel shrink-0">
          {meta && <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: meta.color }} />}
          <span className="text-xs font-mono font-bold text-text-primary">{active?.name ?? '—'}</span>
          {active?.isLive
            ? <span className="text-2xs font-mono px-1.5 py-0.5 bg-market-up/20 text-market-up border border-market-up/30">● LIVE</span>
            : <span className="text-2xs font-mono px-1.5 py-0.5 bg-bg-tertiary text-text-muted border border-border-secondary">OFFLINE</span>
          }
          <div className="flex-1" />
          {/* Refresh button — re-resolves video ID */}
          {active && (
            <button onClick={() => refreshChannel(active.id)}
              className="text-2xs font-mono text-text-muted hover:text-text-primary px-2 py-1 border border-border-secondary hover:border-border-primary transition-all"
              title="Refresh stream">
              ↺ REFRESH
            </button>
          )}
          {/* Always-working direct link */}
          {active && (
            <a href={active.liveUrl} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1 bg-accent-yellow text-black text-2xs font-mono font-bold hover:bg-yellow-400 transition-all">
              ↗ OPEN IN YOUTUBE
            </a>
          )}
        </div>

        {/* Player area */}
        <div className="flex-1 relative bg-black">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex items-center gap-2 text-text-muted font-mono text-xs">
                <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
                Resolving live stream...
              </div>
            </div>
          ) : active?.embedUrl ? (
            <iframe
              key={`${active.id}-${iframeKey.current}`}
              src={active.embedUrl}
              className="w-full h-full border-0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
              title={`${active.name} Live`}
            />
          ) : (
            <OfflineScreen channel={active} onRefresh={() => active && refreshChannel(active.id)} />
          )}
        </div>
      </div>
    </div>
  );
};

const OfflineScreen: React.FC<{ channel?: Stream; onRefresh: () => void }> = ({ channel, onRefresh }) => (
  <div className="absolute inset-0 flex flex-col items-center justify-center text-text-muted font-mono gap-4">
    <div className="text-5xl opacity-20">📺</div>
    <div className="text-sm text-text-secondary">
      {channel?.isLive === false ? 'Channel is currently offline' : 'Stream unavailable'}
    </div>
    <div className="text-2xs text-text-muted max-w-sm text-center leading-relaxed">
      The channel may not be live right now, or YouTube is blocking the embed.
      Use the button below to watch directly.
    </div>
    <div className="flex items-center gap-3">
      <button onClick={onRefresh}
        className="px-4 py-1.5 border border-border-primary text-text-muted text-xs font-mono hover:text-text-primary hover:border-border-accent transition-all">
        ↺ TRY AGAIN
      </button>
      {channel && (
        <a href={channel.liveUrl} target="_blank" rel="noopener noreferrer"
          className="px-6 py-1.5 bg-accent-yellow text-black font-mono font-bold text-xs hover:bg-yellow-400 transition-all">
          ↗ WATCH ON YOUTUBE
        </a>
      )}
    </div>
    {channel && (
      <div className="text-2xs text-text-muted opacity-50">{channel.liveUrl}</div>
    )}
  </div>
);
