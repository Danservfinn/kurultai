'use client';

interface SystemHealthProps {
  health: {
    neo4j: string;
    openclaw: string;
    signal: string;
  };
}

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-green-500',
  ok: 'bg-green-500',
  degraded: 'bg-yellow-500',
  unhealthy: 'bg-red-500',
  unavailable: 'bg-red-500',
  unknown: 'bg-slate-500',
  fallback: 'bg-yellow-500',
};

export function SystemHealth({ health }: SystemHealthProps) {
  const services = [
    { name: 'Neo4j', status: health.neo4j },
    { name: 'OpenClaw', status: health.openclaw },
    { name: 'Signal', status: health.signal },
  ];

  const allHealthy = services.every(s => s.status === 'healthy' || s.status === 'ok');
  const anyUnhealthy = services.some(s => s.status === 'unhealthy' || s.status === 'unavailable');

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${allHealthy ? 'bg-green-500' : anyUnhealthy ? 'bg-red-500' : 'bg-yellow-500'} animate-pulse`} />
        <span className="text-sm text-slate-400">
          {allHealthy ? 'All Systems Operational' : anyUnhealthy ? 'System Issues' : 'Degraded'}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {services.map(service => (
          <div
            key={service.name}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-800/50 border border-slate-700"
            title={`${service.name}: ${service.status}`}
          >
            <div className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[service.status] || 'bg-slate-500'}`} />
            <span className="text-xs text-slate-400">{service.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
