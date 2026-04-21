import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../utils/api";

interface NewsItem {
  headline: string;
  link: string;
  source: string;
  category: string;
  sentiment: "BULLISH" | "BEARISH" | "NEUTRAL";
  tags: string[];
  pub_date: string;
  ts: number;
}

const SENTIMENT_COLOR: Record<string, string> = {
  BULLISH: "#00c853", BEARISH: "#ff1744", NEUTRAL: "#00d4ff",
};
const SENTIMENT_BG: Record<string, string> = {
  BULLISH: "bg-market-up/5 border-market-up/20",
  BEARISH: "bg-market-down/5 border-market-down/20",
  NEUTRAL: "bg-bg-panel border-border-primary",
};

const CATEGORIES = ["ALL","MARKET","OPTIONS","MACRO","SECTOR","FLOWS","GENERAL","GLOBAL","EXCHANGE"];

export const NewsTab: React.FC = () => {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [summary, setSummary] = useState({ bullish: 0, bearish: 0, neutral: 0, score: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");
  const [activeCategory, setActiveCategory] = useState("ALL");
  const [activeSentiment, setActiveSentiment] = useState("ALL");
  const [search, setSearch] = useState("");

  const fetchNews = useCallback(async () => {
    try {
      const res = await api.getNews(activeCategory, activeSentiment) as any;
      if (res.items) {
        setItems(res.items);
        setSummary(res.sentiment_summary || { bullish: 0, bearish: 0, neutral: 0, score: 0 });
        setLastUpdated(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }));
        setError("");
      }
    } catch (e: any) {
      setError(e.message || "Failed to load news");
    } finally {
      setLoading(false);
    }
  }, [activeCategory, activeSentiment]);

  useEffect(() => {
    setLoading(true);
    fetchNews();
    const t = setInterval(fetchNews, 300000); // refresh every 5 min
    return () => clearInterval(t);
  }, [fetchNews]);

  const filtered = items.filter(n => {
    if (!search) return true;
    const q = search.toLowerCase();
    return n.headline.toLowerCase().includes(q) || n.tags.some(t => t.toLowerCase().includes(q));
  });

  return (
    <div className="flex h-full overflow-hidden bg-bg-primary">
      {/* Sidebar */}
      <div className="w-52 shrink-0 border-r border-border-primary flex flex-col overflow-y-auto">
        {/* Sentiment Summary */}
        <div className="p-3 border-b border-border-primary">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">MARKET SENTIMENT</div>
          <div className="flex gap-1 mb-2">
            <div className="flex-1 text-center p-1.5 border border-market-up/30 bg-market-up/10">
              <div className="text-lg font-mono font-bold text-market-up">{summary.bullish}</div>
              <div className="text-2xs font-mono text-text-muted">BULL</div>
            </div>
            <div className="flex-1 text-center p-1.5 border border-market-down/30 bg-market-down/10">
              <div className="text-lg font-mono font-bold text-market-down">{summary.bearish}</div>
              <div className="text-2xs font-mono text-text-muted">BEAR</div>
            </div>
            <div className="flex-1 text-center p-1.5 border border-border-primary bg-bg-panel">
              <div className="text-lg font-mono font-bold text-accent-cyan">{summary.neutral}</div>
              <div className="text-2xs font-mono text-text-muted">NEUT</div>
            </div>
          </div>
          <div className="h-1.5 bg-bg-tertiary relative">
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-primary" />
            <div className="absolute top-0 bottom-0 transition-all"
              style={{
                backgroundColor: summary.score >= 0 ? "#00c853" : "#ff1744",
                left: summary.score >= 0 ? "50%" : `${50 + summary.score / 2}%`,
                width: `${Math.abs(summary.score) / 2}%`,
              }} />
          </div>
          <div className="text-2xs font-mono text-center mt-1"
            style={{ color: summary.score >= 0 ? "#00c853" : "#ff1744" }}>
            {summary.score >= 0 ? "+" : ""}{summary.score} SCORE
          </div>
        </div>

        {/* Sentiment filter */}
        <div className="p-2 border-b border-border-primary">
          <div className="text-2xs font-mono text-text-muted mb-1.5 tracking-widest">SENTIMENT</div>
          {["ALL","BULLISH","BEARISH","NEUTRAL"].map(s => (
            <button key={s} onClick={() => setActiveSentiment(s)}
              className={`w-full text-left px-2 py-1 text-2xs font-mono mb-0.5 border transition-all ${activeSentiment === s ? "border-accent-yellow text-accent-yellow bg-accent-yellow/10" : "border-transparent text-text-muted hover:text-text-secondary"}`}>
              {s !== "ALL" && <span className="mr-1.5" style={{ color: SENTIMENT_COLOR[s] }}>●</span>}
              {s}
            </button>
          ))}
        </div>

        {/* Category filter */}
        <div className="p-2 flex-1 overflow-y-auto">
          <div className="text-2xs font-mono text-text-muted mb-1.5 tracking-widest">CATEGORY</div>
          {CATEGORIES.map(cat => (
            <button key={cat} onClick={() => setActiveCategory(cat)}
              className={`w-full text-left px-2 py-0.5 text-2xs font-mono mb-0.5 border transition-all ${activeCategory === cat ? "border-accent-yellow text-accent-yellow bg-accent-yellow/10" : "border-transparent text-text-muted hover:text-text-secondary"}`}>
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* News feed */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <div className="px-3 py-2 border-b border-border-primary shrink-0">
          <input type="text" placeholder="Search headlines, tags..."
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-bg-tertiary border border-border-primary text-text-primary font-mono text-xs px-3 py-1.5 focus:outline-none focus:border-accent-yellow placeholder-text-muted" />
        </div>
        <div className="px-3 py-1 border-b border-border-secondary shrink-0 flex items-center gap-2">
          <span className="text-2xs font-mono text-text-muted">{filtered.length} stories</span>
          {lastUpdated && <><span className="text-2xs font-mono text-text-muted">·</span>
          <span className="text-2xs font-mono text-text-muted">Updated: {lastUpdated}</span></>}
          {loading && <span className="text-2xs font-mono text-accent-yellow animate-pulse ml-auto">LOADING...</span>}
          {error && <span className="text-2xs font-mono text-market-down ml-auto">⚠ {error} — showing cached</span>}
        </div>
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 && !loading ? (
            <div className="flex items-center justify-center h-32 text-text-muted font-mono text-xs">
              {error ? "Could not load live news" : "No stories match your filters"}
            </div>
          ) : (
            filtered.map((item, i) => <NewsCard key={i} item={item} />)
          )}
        </div>
      </div>
    </div>
  );
};

const NewsCard: React.FC<{ item: NewsItem }> = ({ item }) => (
  <a href={item.link || "#"} target="_blank" rel="noopener noreferrer"
    className={`block px-4 py-3 border-b border-border-secondary hover:bg-bg-hover transition-colors ${SENTIMENT_BG[item.sentiment]}`}>
    <div className="flex items-start gap-3">
      <div className="w-1 self-stretch rounded-full shrink-0 mt-0.5"
        style={{ backgroundColor: SENTIMENT_COLOR[item.sentiment] }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-2xs font-mono font-bold px-1.5 py-0.5 border"
            style={{ color: SENTIMENT_COLOR[item.sentiment], borderColor: SENTIMENT_COLOR[item.sentiment] + "40" }}>
            {item.category}
          </span>
          <span className="text-2xs font-mono text-text-muted">{item.source}</span>
          <span className="text-2xs font-mono text-text-muted ml-auto">
            {item.pub_date ? new Date(item.pub_date).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit" }) : ""}
          </span>
        </div>
        <p className="text-xs font-mono text-text-primary leading-relaxed mb-1.5">{item.headline}</p>
        <div className="flex flex-wrap gap-1">
          {item.tags.map(tag => (
            <span key={tag} className="text-2xs font-mono text-text-muted px-1.5 py-0.5 bg-bg-tertiary border border-border-secondary">
              #{tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  </a>
);
