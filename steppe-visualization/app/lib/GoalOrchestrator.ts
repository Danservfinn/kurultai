/**
 * GoalOrchestrator - Natural Language Command Parser
 *
 * Handles user commands for multi-goal orchestration.
 * Parses natural language into structured actions.
 *
 * Example commands:
 * - "prioritize earnings"
 * - "pause community, focus on freelancing"
 * - "show me everything happening"
 * - "cancel the course goal"
 */

// ============================================================================
// Types
// ============================================================================

export type GoalStatus = 'active' | 'paused' | 'completed' | 'blocked';
export type GoalPriority = 'high' | 'medium' | 'low';

export interface Goal {
  id: string;
  title: string;
  description: string;
  progress: number;
  status: GoalStatus;
  priority: GoalPriority;
  category?: string;
  tags?: string[];
  assignedAgents: string[];
  synergyWith?: string[];
  deadline?: Date;
  createdAt: Date;
}

export interface ParsedCommand {
  type: CommandType;
  confidence: number; // 0-1
  targetGoalIds?: string[]; // Resolved from fuzzy matching
  action: CommandAction;
  params: Record<string, any>;
  rawInput: string;
  explanation?: string; // What Kublai understood
}

export type CommandType =
  | 'status'
  | 'prioritize'
  | 'pause'
  | 'resume'
  | 'cancel'
  | 'remove'
  | 'add'
  | 'modify'
  | 'split'
  | 'merge'
  | 'show'
  | 'hide'
  | 'confirm'
  | 'reject'
  | 'unknown';

export type CommandAction =
  | 'get_status'
  | 'set_priority'
  | 'set_status'
  | 'remove_goal'
  | 'add_goal'
  | 'modify_goal'
  | 'split_goal'
  | 'merge_goals'
  | 'toggle_view'
  | 'confirm_action'
  | 'reject_action';

// ============================================================================
// Keyword Patterns
// ============================================================================

const STATUS_KEYWORDS = ['status', 'progress', 'how', "what's", 'update', 'detail', 'details'];
const PRIORITIZE_KEYWORDS = ['prioritize', 'focus on', 'focus', 'make important', 'first priority', 'top priority'];
const PAUSE_KEYWORDS = ['pause', 'hold', 'stop', 'suspend', 'put on hold', 'wait on'];
const RESUME_KEYWORDS = ['resume', 'continue', 'restart', 'unpause', 'keep going'];
const CANCEL_KEYWORDS = ['cancel', 'remove', 'delete', 'never mind', 'forget', 'drop', 'kill'];
const ADD_KEYWORDS = ['also', 'add', 'plus', 'and also', 'another', 'new goal'];
const SHOW_KEYWORDS = ['show', 'display', 'reveal', 'tell me about', 'explain', 'graph', 'visualize'];
const CONFIRM_KEYWORDS = ['yes', 'confirm', 'proceed', 'do it', 'go ahead', 'ok', 'sure'];
const REJECT_KEYWORDS = ['no', 'cancel', 'stop', "don't", 'nope', 'negative'];

// ============================================================================
// Command Parser
// ============================================================================

export class GoalOrchestrator {
  private goals: Goal[];
  private fuzzyThreshold: number = 0.3; // For fuzzy goal matching

  constructor(goals: Goal[]) {
    this.goals = goals;
  }

  updateGoals(goals: Goal[]): void {
    this.goals = goals;
  }

  /**
   * Parse user input into structured command
   */
  parseCommand(input: string): ParsedCommand {
    const normalized = input.toLowerCase().trim();

    // Check for confirmation/rejection first (short-circuit)
    if (this.matchesKeywords(normalized, CONFIRM_KEYWORDS)) {
      return {
        type: 'confirm',
        confidence: 0.95,
        action: 'confirm_action',
        params: {},
        rawInput: input,
        explanation: 'Confirmed proceeding with action'
      };
    }

    if (this.matchesKeywords(normalized, REJECT_KEYWORDS)) {
      return {
        type: 'reject',
        confidence: 0.95,
        action: 'reject_action',
        params: {},
        rawInput: input,
        explanation: 'Rejected the proposed action'
      };
    }

    // Check for status requests
    if (this.matchesKeywords(normalized, STATUS_KEYWORDS)) {
      const goalIds = this.extractGoalMentions(normalized);

      return {
        type: 'status',
        confidence: 0.9,
        targetGoalIds: goalIds.length > 0 ? goalIds : undefined,
        action: 'get_status',
        params: {
          detailLevel: this.hasDetail(normalized) ? 'full' : 'summary'
        },
        rawInput: input,
        explanation: goalIds.length > 0
          ? `Requesting status for: ${goalIds.length} goal(s)`
          : 'Requesting overall status'
      };
    }

    // Check for prioritize commands
    if (this.matchesKeywords(normalized, PRIORITIZE_KEYWORDS)) {
      const goalIds = this.extractGoalMentions(normalized);

      if (goalIds.length === 0) {
        return {
          type: 'prioritize',
          confidence: 0.5,
          action: 'set_priority',
          params: { priority: 'high' },
          rawInput: input,
          explanation: 'Could not identify which goal to prioritize'
        };
      }

      return {
        type: 'prioritize',
        confidence: 0.9,
        targetGoalIds: goalIds,
        action: 'set_priority',
        params: { priority: 'high' },
        rawInput: input,
        explanation: `Prioritizing: ${goalIds.length} goal(s)`
      };
    }

    // Check for pause commands
    if (this.matchesKeywords(normalized, PAUSE_KEYWORDS)) {
      const goalIds = this.extractGoalMentions(normalized);

      if (goalIds.length === 0) {
        return {
          type: 'pause',
          confidence: 0.5,
          action: 'set_status',
          params: { status: 'paused' },
          rawInput: input,
          explanation: 'Could not identify which goal to pause'
        };
      }

      return {
        type: 'pause',
        confidence: 0.9,
        targetGoalIds: goalIds,
        action: 'set_status',
        params: { status: 'paused' },
        rawInput: input,
        explanation: `Pausing: ${goalIds.length} goal(s)`
      };
    }

    // Check for resume commands
    if (this.matchesKeywords(normalized, RESUME_KEYWORDS)) {
      const goalIds = this.extractGoalMentions(normalized);

      if (goalIds.length === 0) {
        return {
          type: 'resume',
          confidence: 0.5,
          action: 'set_status',
          params: { status: 'active' },
          rawInput: input,
          explanation: 'Could not identify which goal to resume'
        };
      }

      return {
        type: 'resume',
        confidence: 0.9,
        targetGoalIds: goalIds,
        action: 'set_status',
        params: { status: 'active' },
        rawInput: input,
        explanation: `Resuming: ${goalIds.length} goal(s)`
      };
    }

    // Check for cancel commands
    if (this.matchesKeywords(normalized, CANCEL_KEYWORDS)) {
      const goalIds = this.extractGoalMentions(normalized);

      if (goalIds.length === 0) {
        return {
          type: 'cancel',
          confidence: 0.3,
          action: 'remove_goal',
          params: {},
          rawInput: input,
          explanation: 'Ambiguous: Did you mean cancel last action or remove a goal?'
        };
      }

      return {
        type: 'cancel',
        confidence: 0.9,
        targetGoalIds: goalIds,
        action: 'remove_goal',
        params: {},
        rawInput: input,
        explanation: `Removing: ${goalIds.length} goal(s)`
      };
    }

    // Check for show commands
    if (this.matchesKeywords(normalized, SHOW_KEYWORDS)) {
      const detailLevel = this.hasDetail(normalized) ? 'full' : 'summary';
      const showWhat = this.extractShowTarget(normalized);

      return {
        type: 'show',
        confidence: 0.85,
        action: 'toggle_view',
        params: {
          target: showWhat,
          detailLevel
        },
        rawInput: input,
        explanation: showWhat === 'all'
          ? 'Showing all goals and agent assignments'
          : `Showing: ${showWhat}`
      };
    }

    // Default: unknown command
    return {
      type: 'unknown',
      confidence: 0.2,
      action: 'get_status',
      params: {},
      rawInput: input,
      explanation: 'Could not understand the command. Try: "status", "prioritize [goal]", "pause [goal]"'
    };
  }

  /**
   * Extract goal IDs from natural language input using fuzzy matching
   */
  private extractGoalMentions(input: string): string[] {
    const mentions: string[] = [];
    const words = input.split(/\s+/);

    // Direct ID matching (if user references "goal 1", "goal 2", etc.)
    const goalNumberPattern = /goal\s*(\d+)/gi;
    const numberMatches = input.match(goalNumberPattern);
    if (numberMatches) {
      numberMatches.forEach((match) => {
        const num = parseInt(match.replace(/goal\s*/gi, ''));
        if (num > 0 && num <= this.goals.length) {
          mentions.push(this.goals[num - 1].id);
        }
      });
    }

    // Keyword matching against goal titles and tags
    this.goals.forEach((goal) => {
      const titleWords = goal.title.toLowerCase().split(/\s+/);
      const descWords = goal.description.toLowerCase().split(/\s+/);
      const tagWords = (goal.tags || []).map((t) => t.toLowerCase());

      // Check for title word matches
      const titleMatches = words.filter((w) =>
        titleWords.some((tw) => this.similarity(w, tw) > this.fuzzyThreshold)
      );

      // Check for tag matches
      const tagMatches = words.filter((w) =>
        tagWords.some((t) => this.similarity(w, t) > this.fuzzyThreshold)
      );

      if (titleMatches.length > 0 || tagMatches.length > 0) {
        mentions.push(goal.id);
      }
    });

    // Remove duplicates
    return Array.from(new Set(mentions));
  }

  /**
   * Extract what the user wants to see
   */
  private extractShowTarget(input: string): string {
    if (input.includes('everything') || input.includes('all')) return 'all';
    if (input.includes('agent') || input.includes('team')) return 'agents';
    if (input.includes('graph') || input.includes('visual')) return 'graph';
    if (input.includes('timeline') || input.includes('history')) return 'timeline';
    if (input.includes('active')) return 'active';
    if (input.includes('paused')) return 'paused';
    return 'all';
  }

  /**
   * Check if input has detail keywords
   */
  private hasDetail(input: string): boolean {
    const detailKeywords = ['detail', 'detailed', 'full', 'complete', 'everything', 'all', 'comprehensive'];
    return detailKeywords.some((kw) => input.includes(kw));
  }

  /**
   * Check if input matches any of the keyword patterns
   */
  private matchesKeywords(input: string, keywords: string[]): boolean {
    return keywords.some((keyword) => input.includes(keyword));
  }

  /**
   * Simple string similarity (Levenshtein distance ratio)
   */
  private similarity(str1: string, str2: string): number {
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;

    if (longer.length === 0) return 1.0;

    const costs: number[] = [];
    for (let i = 0; i <= longer.length; i++) {
      let lastValue = i;
      for (let j = 0; j <= shorter.length; j++) {
        if (i === 0) {
          costs[j] = j;
        } else if (j > 0) {
          let newValue = costs[j - 1];
          if (longer.charAt(i - 1) !== shorter.charAt(j - 1)) {
            newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
          }
          costs[j - 1] = lastValue;
          lastValue = newValue;
        }
      }
      if (i > 0) costs[shorter.length] = lastValue;
    }

    return (longer.length - costs[shorter.length]) / longer.length;
  }

  /**
   * Generate response for parsed command
   */
  generateResponse(command: ParsedCommand): string {
    switch (command.type) {
      case 'status':
        if (command.targetGoalIds && command.targetGoalIds.length > 0) {
          const goals = this.goals.filter((g) => command.targetGoalIds!.includes(g.id));
          return this.formatGoalStatus(goals, command.params.detailLevel);
        }
        return this.formatOverallStatus(command.params.detailLevel);

      case 'prioritize':
        if (command.targetGoalIds && command.targetGoalIds.length > 0) {
          return `🎯 Prioritizing ${command.targetGoalIds.length} goal(s)\n\nReprioritizing agents and resources.\n\nThis may affect ${this.countAffectedAgents(command.targetGoalIds)} agents' workloads.\n\nConfirm? (yes/no)`;
        }
        return '❓ Which goal would you like to prioritize?';

      case 'pause':
        if (command.targetGoalIds && command.targetGoalIds.length > 0) {
          return `⏸️ Pausing ${command.targetGoalIds.length} goal(s)\n\nAgents will be reassigned.\nReply "resume" to continue these goals.`;
        }
        return '❓ Which goal would you like to pause?';

      case 'resume':
        if (command.targetGoalIds && command.targetGoalIds.length > 0) {
          return `▶️ Resuming ${command.targetGoalIds.length} goal(s)\n\nPicking up where we left off.`;
        }
        return '❓ Which goal would you like to resume?';

      case 'cancel':
        if (command.targetGoalIds && command.targetGoalIds.length > 0) {
          return `❌ Removing ${command.targetGoalIds.length} goal(s)\n\n⚠️ This cannot be undone.\n\nConfirm? (yes/no)`;
        }
        return '❓ Which goal would you like to remove?';

      case 'show':
        return this.formatShowResponse(command.params);

      case 'confirm':
        return '✅ Proceeding with action...';

      case 'reject':
        return '❌ Action cancelled.';

      default:
        return '❓ I didn\'t understand that command.\n\nTry: "status", "prioritize [goal]", "pause [goal]", "resume [goal]", "show [all/agents/graph]"';
    }
  }

  /**
   * Format goal status response
   */
  private formatGoalStatus(goals: Goal[], detailLevel: string): string {
    if (goals.length === 0) return 'No matching goals found.';

    if (detailLevel === 'full') {
      return goals.map((g) => `
🎯 ${g.title}
   Progress: ${g.progress}%
   Status: ${g.status}
   Priority: ${g.priority}
   Agents: ${g.assignedAgents.join(', ')}
   ${g.deadline ? `Deadline: ${g.deadline.toLocaleDateString()}` : ''}
`.trim()).join('\n\n');
    }

    return goals.map((g) => `🎯 ${g.title}: ${g.progress}% complete`).join('\n');
  }

  /**
   * Format overall status response
   */
  private formatOverallStatus(detailLevel: string): string {
    const activeGoals = this.goals.filter((g) => g.status === 'active');
    const pausedGoals = this.goals.filter((g) => g.status === 'paused');
    const completedGoals = this.goals.filter((g) => g.status === 'completed');

    if (detailLevel === 'full') {
      return `
📊 OVERALL STATUS

🎯 ACTIVE (${activeGoals.length})
${activeGoals.map(g => `  • ${g.title}: ${g.progress}%`).join('\n')}

⏸️ PAUSED (${pausedGoals.length})
${pausedGoals.map(g => `  • ${g.title}`).join('\n')}

✅ COMPLETED (${completedGoals.length})
${completedGoals.map(g => `  • ${g.title}`).join('\n')}

Reply "detail [goal name]" for more information on any goal.
`.trim();
    }

    return `📊 ${activeGoals.length} active, ${pausedGoals.length} paused, ${completedGoals.length} completed goals.`;
  }

  /**
   * Format show response
   */
  private formatShowResponse(params: Record<string, any>): string {
    const { target, detailLevel } = params;

    if (target === 'all') {
      return this.formatOverallStatus(detailLevel === 'full' ? 'full' : 'summary');
    }

    if (target === 'agents') {
      // Would show agent workloads
      return '📋 Agent Workload:\n\n(Agent workload display would go here)';
    }

    if (target === 'graph') {
      return '📊 Goal Graph:\n\n(Interactive graph visualization would open)';
    }

    return `Showing: ${target}`;
  }

  /**
   * Count agents affected by goal changes
   */
  private countAffectedAgents(goalIds: string[]): number {
    const affectedAgents = new Set<string>();
    goalIds.forEach((goalId) => {
      const goal = this.goals.find((g) => g.id === goalId);
      if (goal) {
        goal.assignedAgents.forEach((agentId) => affectedAgents.add(agentId));
      }
    });
    return affectedAgents.size;
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Create a mock goal for testing
 */
export function createMockGoal(overrides?: Partial<Goal>): Goal {
  return {
    id: `goal-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    title: 'Sample Goal',
    description: 'A sample goal for testing',
    progress: 0,
    status: 'active',
    priority: 'medium',
    assignedAgents: [],
    createdAt: new Date(),
    ...overrides
  };
}

/**
 * Create sample goals for demonstration
 */
export function createSampleGoals(): Goal[] {
  return [
    {
      id: 'goal-earnings',
      title: 'Earn 1,000 USDC',
      description: 'Generate $1,000 in revenue through freelance work',
      progress: 80,
      status: 'active',
      priority: 'high',
      category: 'Earnings',
      tags: ['freelance', 'earnings', 'money'],
      assignedAgents: ['mongke', 'temujin', 'chagatai'],
      synergyWith: ['goal-community'],
      deadline: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
      createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000) // 3 days ago
    },
    {
      id: 'goal-community',
      title: 'Start Money-Making Community',
      description: 'Launch a Discord community for freelancers to share opportunities',
      progress: 40,
      status: 'active',
      priority: 'medium',
      category: 'Community',
      tags: ['community', 'discord', 'networking'],
      assignedAgents: ['ogedei', 'jochi', 'chagatai'],
      synergyWith: ['goal-earnings'],
      deadline: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000), // 14 days
      createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000) // 5 days ago
    },
    {
      id: 'goal-course',
      title: 'Create Online Course',
      description: 'Build and launch a comprehensive freelance course',
      progress: 20,
      status: 'paused',
      priority: 'low',
      category: 'Products',
      tags: ['course', 'product', 'passive-income'],
      assignedAgents: ['chagatai', 'temujin'],
      deadline: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000), // 30 days
      createdAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000) // 10 days ago
    }
  ];
}
