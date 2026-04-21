import React from 'react';

const Pulse: React.FC<{ w?: string; h?: string; className?: string }> = ({
  w = 'w-full', h = 'h-4', className = '',
}) => (
  <div className={`${w} ${h} bg-bg-tertiary animate-pulse ${className}`} />
);

export const ChainSkeleton: React.FC = () => (
  <div className="p-3 flex flex-col gap-2 flex-1">
    {/* Header */}
    <div className="flex gap-2 mb-2">
      {[...Array(6)].map((_, i) => (
        <Pulse key={i} w="w-16" h="h-5" />
      ))}
    </div>
    {/* Rows */}
    {[...Array(18)].map((_, i) => (
      <div key={i} className="flex gap-2 items-center">
        <Pulse w="w-24" h="h-5" />
        <Pulse w="w-16" h="h-5" />
        <Pulse w="w-12" h="h-5" />
        <Pulse w="w-10" h="h-5" />
        {/* Strike */}
        <Pulse w="w-20" h="h-6" className="bg-bg-hover" />
        <Pulse w="w-10" h="h-5" />
        <Pulse w="w-12" h="h-5" />
        <Pulse w="w-16" h="h-5" />
        <Pulse w="w-24" h="h-5" />
      </div>
    ))}
  </div>
);

export const ChartSkeleton: React.FC<{ height?: number }> = ({ height = 160 }) => (
  <div className="w-full animate-pulse" style={{ height }}>
    <div className="w-full h-full bg-bg-tertiary" />
  </div>
);

export const MetricsSkeleton: React.FC = () => (
  <div className="grid grid-cols-4 gap-2">
    {[...Array(4)].map((_, i) => (
      <div key={i} className="border border-border-secondary bg-bg-panel p-3">
        <Pulse w="w-16" h="h-3" className="mb-2" />
        <Pulse w="w-24" h="h-7" className="mb-1" />
        <Pulse w="w-20" h="h-2" />
      </div>
    ))}
  </div>
);

export const LoadingOverlay: React.FC<{ label?: string }> = ({ label = 'LOADING' }) => (
  <div className="absolute inset-0 flex items-center justify-center bg-bg-primary/80 z-50">
    <div className="text-center">
      <div className="flex gap-1 justify-center mb-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-2 h-2 bg-accent-yellow"
            style={{ animation: `pulse 1s ease-in-out ${i * 0.2}s infinite` }}
          />
        ))}
      </div>
      <div className="text-accent-yellow font-mono text-xs tracking-widest animate-blink">
        {label}
      </div>
    </div>
  </div>
);
