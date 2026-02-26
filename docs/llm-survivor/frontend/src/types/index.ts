export interface GameState {
  season_id: number;
  current_day: number;
  phase: 'challenge' | 'scramble' | 'tribal' | 'memory' | 'completed' | 'finale_running';
  is_merged: boolean;
  winner: string | null;
}

export interface Agent {
  agent_id: string;
  pseudonym: string;
  team_id: string;
  status: 'active' | 'eliminated' | 'jury';
  has_immunity: boolean;
  confessional_memory: string;
  action_points: number;
}

export interface Message {
  id: number;
  day: number;
  sender_id: string;
  receiver_ids: string[];
  is_public: boolean;
  inner_thought: string;
  content: string;
  trust_telemetry: Record<string, number>;
  timestamp: string;
}

export interface Vote {
  voter_id: string;
  target_id: string;
  target_pseudonym: string;
}

export interface ApiStateResponse {
  game: GameState;
  agents: Agent[];
  messages: Message[];
  votes: Vote[];
}
