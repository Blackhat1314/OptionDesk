import React, { useState, useEffect } from "react";

interface ContentBlock {
  type: "para" | "formula" | "table" | "example" | "signal" | "tip" | "warning";
  text?: string;
  label?: string;
  color?: string;
  headers?: string[];
  rows?: string[][];
}

interface Topic {
  id: string;
  title: string;
  content: ContentBlock[];
}

interface Section {
  id: string;
  title: string;
  icon: string;
  color: string;
  topics: Topic[];
}

export const GuideTab: React.FC = () => {
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState("");
  const [activeTopic, setActiveTopic] = useState("");

  useEffect(() => {
    fetch("/api/guide")
      .then(r => r.json())
      .then(data => {
        const secs: Section[] = data.sections || [];
        setSections(secs);
        if (secs.length > 0) {
          setActiveSection(secs[0].id);
          setActiveTopic(secs[0].topics[0]?.id || "");
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted font-mono text-xs">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
          LOADING GUIDE...
        </div>
      </div>
    );
  }

  if (!sections.length) {
    return (
      <div className="flex items-center justify-center h-full text-market-down font-mono text-xs">
        Failed to load guide content
      </div>
    );
  }

  const section = sections.find(s => s.id === activeSection) || sections[0];
  const topic = section.topics.find(t => t.id === activeTopic) || section.topics[0];
  const topicIdx = section.topics.findIndex(t => t.id === activeTopic);
  const prevTopic = section.topics[topicIdx - 1];
  const nextTopic = section.topics[topicIdx + 1];

  const handleSectionChange = (sid: string) => {
    setActiveSection(sid);
    const sec = sections.find(s => s.id === sid);
    if (sec?.topics[0]) setActiveTopic(sec.topics[0].id);
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg-primary">
      {/* Sidebar */}
      <div className="w-56 shrink-0 border-r border-border-primary flex flex-col bg-bg-secondary overflow-y-auto">
        <div className="px-3 py-2 border-b border-border-primary flex items-center gap-2">
          <span className="text-accent-yellow">📖</span>
          <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">GUIDE & LEARN</span>
        </div>
        {sections.map(sec => (
          <div key={sec.id}>
            <button
              onClick={() => handleSectionChange(sec.id)}
              className={`w-full text-left px-3 py-2 border-b border-border-secondary transition-all ${
                activeSection === sec.id
                  ? "bg-accent-yellow/10 border-l-2"
                  : "hover:bg-bg-hover"
              }`}
              style={{ borderLeftColor: activeSection === sec.id ? sec.color : "transparent" }}
            >
              <div className="flex items-center gap-2">
                <span className="text-base">{sec.icon}</span>
                <span className={`text-xs font-mono font-bold ${activeSection === sec.id ? "text-text-primary" : "text-text-muted"}`}>
                  {sec.title}
                </span>
              </div>
            </button>
            {activeSection === sec.id && sec.topics.map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTopic(t.id)}
                className={`w-full text-left pl-8 pr-3 py-1.5 border-b border-border-secondary/40 transition-all text-2xs font-mono ${
                  activeTopic === t.id
                    ? "text-accent-yellow bg-accent-yellow/5"
                    : "text-text-muted hover:text-text-secondary hover:bg-bg-hover"
                }`}
              >
                {activeTopic === t.id ? "▶ " : "  "}{t.title}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border-primary bg-bg-panel sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{section.icon}</span>
            <div>
              <div className="text-2xs font-mono text-text-muted tracking-widest uppercase">{section.title}</div>
              <div className="text-lg font-mono font-bold text-text-primary">{topic?.title}</div>
            </div>
          </div>
        </div>

        {/* Blocks */}
        <div className="px-6 py-5 space-y-4 max-w-4xl">
          {topic?.content.map((block, i) => (
            <Block key={i} block={block} />
          ))}

          {/* Prev / Next */}
          <div className="flex items-center justify-between pt-6 border-t border-border-primary mt-6">
            {prevTopic ? (
              <button
                onClick={() => setActiveTopic(prevTopic.id)}
                className="flex items-center gap-2 px-4 py-2 border border-border-primary text-text-muted hover:text-text-primary hover:border-accent-yellow/50 transition-all font-mono text-xs"
              >
                ← {prevTopic.title}
              </button>
            ) : <div />}
            {nextTopic ? (
              <button
                onClick={() => setActiveTopic(nextTopic.id)}
                className="flex items-center gap-2 px-4 py-2 border border-border-primary text-text-muted hover:text-text-primary hover:border-accent-yellow/50 transition-all font-mono text-xs"
              >
                {nextTopic.title} →
              </button>
            ) : <div />}
          </div>
        </div>
      </div>
    </div>
  );
};

const Block: React.FC<{ block: ContentBlock }> = ({ block }) => {
  switch (block.type) {
    case "para":
      return <p className="text-sm font-mono text-text-secondary leading-relaxed">{block.text}</p>;

    case "formula":
      return (
        <div className="bg-bg-tertiary border border-accent-yellow/30 px-4 py-3 font-mono text-sm">
          <span className="text-2xs text-text-muted mr-2 tracking-widest">FORMULA</span>
          <span className="text-accent-yellow">{block.text}</span>
        </div>
      );

    case "example":
      return (
        <div className="bg-bg-panel border border-border-primary border-l-4 px-4 py-3" style={{ borderLeftColor: "#00d4ff" }}>
          <div className="text-2xs font-mono font-bold text-accent-cyan mb-1">💡 {block.label}</div>
          <p className="text-sm font-mono text-text-secondary leading-relaxed">{block.text}</p>
        </div>
      );

    case "signal":
      return (
        <div className="border px-4 py-3 rounded-sm" style={{
          borderColor: (block.color || "#607d8b") + "60",
          backgroundColor: (block.color || "#607d8b") + "12"
        }}>
          <div className="text-2xs font-mono font-bold mb-1" style={{ color: block.color }}>
            ⚡ {block.label}
          </div>
          <p className="text-sm font-mono leading-relaxed" style={{ color: block.color }}>{block.text}</p>
        </div>
      );

    case "tip":
      return (
        <div className="bg-market-up/5 border border-market-up/30 border-l-4 border-l-market-up px-4 py-3">
          <div className="text-2xs font-mono font-bold text-market-up mb-1">💡 TIP</div>
          <p className="text-sm font-mono text-text-secondary leading-relaxed">{block.text}</p>
        </div>
      );

    case "warning":
      return (
        <div className="bg-market-down/5 border border-market-down/30 border-l-4 border-l-market-down px-4 py-3">
          <div className="text-2xs font-mono font-bold text-market-down mb-1">⚠️ WARNING</div>
          <p className="text-sm font-mono text-text-secondary leading-relaxed">{block.text}</p>
        </div>
      );

    case "table":
      return (
        <div className="border border-border-primary overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="bg-bg-panel border-b border-border-primary">
                {block.headers?.map((h, i) => (
                  <th key={i} className="text-left px-3 py-2 text-accent-yellow font-bold text-2xs tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows?.map((row, ri) => (
                <tr key={ri} className={`border-b border-border-secondary/40 hover:bg-bg-hover ${ri % 2 === 0 ? "bg-bg-primary" : "bg-bg-panel"}`}>
                  {row.map((cell, ci) => (
                    <td key={ci} className={`px-3 py-2 leading-relaxed ${ci === 0 ? "text-text-primary font-bold whitespace-nowrap" : "text-text-secondary"}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    default:
      return null;
  }
};
