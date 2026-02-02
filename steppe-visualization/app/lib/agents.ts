import { Agent } from '@/app/types/agents';

// Convert lat/lng to 3D world coordinates
// Mongol Empire bounds at its height (1279): 22°E to 135°E, 22°N to 55°N
const MAP_BOUNDS = {
  minLat: 22,
  maxLat: 55,
  minLng: 22,
  maxLng: 135,
};

export function latLngToWorld(lat: number, lng: number): { x: number; z: number } {
  const x = ((lng - MAP_BOUNDS.minLng) / (MAP_BOUNDS.maxLng - MAP_BOUNDS.minLng)) * 120 - 60;
  const z = ((lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat)) * -70 + 35;
  return { x, z };
}

export function getElevation(lat: number, lng: number): number {
  // Flat elevation - very minimal variation for the new flat terrain
  return 0.5;
}

export const AGENTS: Agent[] = [
  {
    id: 'temujin',
    name: 'Temujin',
    role: 'developer',
    displayName: 'Temujin (Genghis Khan)',
    description: 'Founder of the Mongol Empire and the Developer agent - building the foundation',
    historicalCapital: 'Karakorum',
    historicalContext: 'Established Karakorum as the supply base in 1220. The original capital of the Mongol Empire.',
    coordinates: { lat: 47.2, lng: 102.5 },
    position: { ...latLngToWorld(47.2, 102.5), elevation: getElevation(47.2, 102.5) },
    theme: {
      primary: '#71717A',
      secondary: '#DC2626',
      glow: '#DC2626',
    },
    status: 'working',
    currentTask: {
      id: 'task-1',
      title: 'Refactoring core architecture',
      description: 'Optimizing the main codebase structure',
      progress: 65,
      startedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
      estimatedCompletion: new Date(Date.now() + 1 * 60 * 60 * 1000),
    },
    queue: [
      { id: 'q1', title: 'Security audit', priority: 'high', estimatedDuration: 120 },
      { id: 'q2', title: 'API optimization', priority: 'medium', estimatedDuration: 90 },
      { id: 'q3', title: 'Database migration', priority: 'high', estimatedDuration: 180 },
    ],
    metrics: {
      tasksCompleted: 12,
      itemsProduced: 8,
      activeTimeMinutes: 340,
      lastActiveAt: new Date(),
    },
    camp: {
      type: 'forge',
      description: 'A warrior\'s workshop with tools and armor',
      props: ['anvil', 'weapons', 'banners'],
    },
  },
  {
    id: 'ogedei',
    name: 'Ogedei',
    role: 'writer',
    displayName: 'Ögedei Khan',
    description: 'Second Great Khan and the Writer agent - crafting content and documentation',
    historicalCapital: 'Samarkand',
    historicalContext: 'While he ruled from Karakorum, Samarkand represents his expansion into Central Asia and the Silk Road.',
    coordinates: { lat: 39.6, lng: 66.9 },
    position: { ...latLngToWorld(39.6, 66.9), elevation: getElevation(39.6, 66.9) },
    theme: {
      primary: '#228B22',
      secondary: '#8B4513',
      glow: '#228B22',
    },
    status: 'working',
    currentTask: {
      id: 'task-2',
      title: 'Writing documentation',
      description: 'Creating API reference docs',
      progress: 40,
      startedAt: new Date(Date.now() - 1 * 60 * 60 * 1000),
      estimatedCompletion: new Date(Date.now() + 2 * 60 * 60 * 1000),
    },
    queue: [
      { id: 'q4', title: 'Blog post draft', priority: 'medium', estimatedDuration: 60 },
      { id: 'q5', title: 'User guide update', priority: 'high', estimatedDuration: 120 },
    ],
    metrics: {
      tasksCompleted: 8,
      itemsProduced: 15,
      activeTimeMinutes: 280,
      lastActiveAt: new Date(),
    },
    camp: {
      type: 'caravanserai',
      description: 'A bustling Silk Road trading post with scrolls and maps',
      props: ['scrolls', 'maps', 'trading goods'],
    },
  },
  {
    id: 'mongke',
    name: 'Mongke',
    role: 'researcher',
    displayName: 'Möngke Khan',
    description: 'Fourth Great Khan and the Researcher agent - gathering intelligence and knowledge',
    historicalCapital: 'Bukhara',
    historicalContext: 'Bukhara was a center of Islamic learning. Mongke conducted empire-wide censuses and sent expeditions to gather knowledge.',
    coordinates: { lat: 39.8, lng: 64.4 },
    position: { ...latLngToWorld(39.8, 64.4), elevation: getElevation(39.8, 64.4) },
    theme: {
      primary: '#1E40AF',
      secondary: '#C0C0C0',
      glow: '#1E40AF',
    },
    status: 'reviewing',
    currentTask: {
      id: 'task-3',
      title: 'Market analysis report',
      description: 'Analyzing competitor strategies',
      progress: 85,
      startedAt: new Date(Date.now() - 3 * 60 * 60 * 1000),
      estimatedCompletion: new Date(Date.now() + 30 * 60 * 1000),
    },
    queue: [
      { id: 'q6', title: 'User research study', priority: 'high', estimatedDuration: 240 },
      { id: 'q7', title: 'Data collection', priority: 'medium', estimatedDuration: 90 },
      { id: 'q8', title: 'Trend analysis', priority: 'low', estimatedDuration: 120 },
    ],
    metrics: {
      tasksCompleted: 6,
      itemsProduced: 4,
      activeTimeMinutes: 420,
      lastActiveAt: new Date(),
    },
    camp: {
      type: 'observatory',
      description: 'A scholarly retreat with astronomical instruments and manuscripts',
      props: ['telescope', 'books', 'astrolabe'],
    },
  },
  {
    id: 'kublai',
    name: 'Kublai',
    role: 'coordinator',
    displayName: 'Kublai Khan',
    description: 'First Yuan Emperor and the Coordinator agent - orchestrating the empire',
    historicalCapital: 'Shangdu (Xanadu)',
    historicalContext: 'Founded Shangdu (Xanadu) in 1256 as his summer capital before moving to Dadu (Beijing).',
    coordinates: { lat: 42.3, lng: 116.2 },
    position: { ...latLngToWorld(42.3, 116.2), elevation: getElevation(42.3, 116.2) },
    theme: {
      primary: '#FFD700',
      secondary: '#1E3A8A',
      glow: '#FFD700',
    },
    status: 'working',
    currentTask: {
      id: 'task-4',
      title: 'Strategic planning',
      description: 'Coordinating cross-team initiatives',
      progress: 25,
      startedAt: new Date(Date.now() - 30 * 60 * 1000),
      estimatedCompletion: new Date(Date.now() + 3 * 60 * 60 * 1000),
    },
    queue: [
      { id: 'q9', title: 'Review PRs', priority: 'high', estimatedDuration: 60 },
      { id: 'q10', title: 'Team sync', priority: 'medium', estimatedDuration: 30 },
      { id: 'q11', title: 'Q1 roadmap', priority: 'high', estimatedDuration: 180 },
    ],
    metrics: {
      tasksCompleted: 20,
      itemsProduced: 12,
      activeTimeMinutes: 380,
      lastActiveAt: new Date(),
    },
    camp: {
      type: 'palace',
      description: 'An imperial palace with gardens and administrative halls',
      props: ['throne', 'banners', 'imperial seals'],
    },
  },
  {
    id: 'chagatai',
    name: 'Chagatai',
    role: 'operations',
    displayName: 'Chagatai Khan',
    description: 'Founder of the Chagatai Khanate and the Operations agent - managing logistics',
    historicalCapital: 'Almaliq',
    historicalContext: 'Almaliq in the Ili River Valley was a key city in the Chagatai Khanate, controlling the northern Silk Road.',
    coordinates: { lat: 44.0, lng: 78.5 },
    position: { ...latLngToWorld(44.0, 78.5), elevation: getElevation(44.0, 78.5) },
    theme: {
      primary: '#EA580C',
      secondary: '#CD7F32',
      glow: '#EA580C',
    },
    status: 'working',
    currentTask: {
      id: 'task-5',
      title: 'Infrastructure scaling',
      description: 'Setting up new server instances',
      progress: 55,
      startedAt: new Date(Date.now() - 4 * 60 * 60 * 1000),
      estimatedCompletion: new Date(Date.now() + 2 * 60 * 60 * 1000),
    },
    queue: [
      { id: 'q12', title: 'CI/CD pipeline update', priority: 'high', estimatedDuration: 90 },
      { id: 'q13', title: 'Monitoring setup', priority: 'medium', estimatedDuration: 60 },
    ],
    metrics: {
      tasksCompleted: 15,
      itemsProduced: 6,
      activeTimeMinutes: 460,
      lastActiveAt: new Date(),
    },
    camp: {
      type: 'caravanserai',
      description: 'A fortified waystation on the Silk Road',
      props: ['horses', 'supplies', 'route maps'],
    },
  },
  {
    id: 'jochi',
    name: 'Jochi',
    role: 'analyst',
    displayName: 'Jochi Khan',
    description: 'Eldest son of Genghis Khan and the Analyst agent - tracking metrics and intelligence',
    historicalCapital: 'Sarai Batu',
    historicalContext: 'Sarai Batu on the lower Volga was the capital of the Golden Horde, controlling trade and tribute from Russia.',
    coordinates: { lat: 48.5, lng: 45.0 },
    position: { ...latLngToWorld(48.5, 45.0), elevation: getElevation(48.5, 45.0) },
    theme: {
      primary: '#7C3AED',
      secondary: '#F59E0B',
      glow: '#7C3AED',
    },
    status: 'idle',
    queue: [
      { id: 'q14', title: 'Performance metrics', priority: 'high', estimatedDuration: 120 },
      { id: 'q15', title: 'Revenue analysis', priority: 'high', estimatedDuration: 90 },
      { id: 'q16', title: 'User behavior report', priority: 'medium', estimatedDuration: 150 },
    ],
    metrics: {
      tasksCompleted: 10,
      itemsProduced: 7,
      activeTimeMinutes: 290,
      lastActiveAt: new Date(Date.now() - 30 * 60 * 1000),
    },
    camp: {
      type: 'counting-house',
      description: 'A administrative center with tribute records and trade ledgers',
      props: ['abacus', 'scrolls', 'tribute goods'],
    },
  },
];

export function getAgentById(id: string): Agent | undefined {
  return AGENTS.find(a => a.id === id);
}

export function getAgentColor(role: Agent['role']): string {
  const colors: Record<Agent['role'], string> = {
    coordinator: '#FFD700',
    researcher: '#1E40AF',
    writer: '#228B22',
    developer: '#DC2626',
    analyst: '#7C3AED',
    operations: '#EA580C',
  };
  return colors[role];
}
