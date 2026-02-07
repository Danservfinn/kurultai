/**
 * GoalOrchestrator Usage Examples
 *
 * This file demonstrates how to use the GoalOrchestrator
 * for natural language command processing in the Kublai system.
 */

import { GoalOrchestrator, createSampleGoals } from './GoalOrchestrator';

// ============================================================================
// Example 1: Basic Command Parsing
// ============================================================================

function example1_BasicParsing() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  const commands = [
    'status',
    'prioritize earnings',
    'pause community',
    'resume course',
    'cancel the course goal',
    'show me everything'
  ];

  console.log('=== Example 1: Basic Command Parsing ===\n');

  commands.forEach((cmd) => {
    const parsed = orchestrator.parseCommand(cmd);
    const response = orchestrator.generateResponse(parsed);

    console.log(`User: ${cmd}`);
    console.log(`Parsed: ${JSON.stringify(parsed, null, 2)}`);
    console.log(`Response:\n${response}\n`);
    console.log('---\n');
  });
}

// ============================================================================
// Example 2: Synergistic Goal Detection
// ============================================================================

function example2_SynergyDetection() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  // User sends multiple rapid goals
  const userMessages = [
    'Earn 1,000 USDC',
    'Start money-making community'
  ];

  console.log('=== Example 2: Synergistic Goal Detection ===\n');

  console.log('User sends multiple rapid goals:');
  userMessages.forEach((msg) => console.log(`  - ${msg}`));

  // Detect synergies
  const synergisticGoals = goals.filter((g) =>
    g.synergyWith && g.synergyWith.length > 0
  );

  console.log('\nKublai detects synergies:');
  synergisticGoals.forEach((goal) => {
    console.log(`  💡 ${goal.title} connects to:`);
    goal.synergyWith!.forEach((synergyId) => {
      const connectedGoal = goals.find((g) => g.id === synergyId);
      if (connectedGoal) {
        console.log(`     → ${connectedGoal.title}`);
      }
    });
  });

  console.log('\nKublai response:');
  console.log('💡 These work together—building unified strategy');
  console.log('   Earnings fund community, community amplifies earnings');
  console.log('\n   📋 INTEGRATED PLAN:');
  console.log('   Week 1: Quick earnings (freelance sprints)');
  console.log('   Week 2: Community MVP launch');
  console.log('   Week 3: Merge (community referral program)');
}

// ============================================================================
// Example 3: Mid-Course Correction
// ============================================================================

function example3_MidCourseCorrection() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  console.log('=== Example 3: Mid-Course Correction ===\n');

  // User changes priority
  const userCommand = 'pause community, focus on freelancing';
  const parsed = orchestrator.parseCommand(userCommand);

  console.log(`User: ${userCommand}`);
  console.log(`\nParsed command:`);
  console.log(`  Type: ${parsed.type}`);
  console.log(`  Confidence: ${parsed.confidence}`);
  console.log(`  Target goals: ${parsed.targetGoalIds?.length || 0}`);

  if (parsed.targetGoalIds && parsed.targetGoalIds.length > 0) {
    const affectedGoals = goals.filter((g) =>
      parsed.targetGoalIds!.includes(g.id)
    );

    console.log('\nAffected goals:');
    affectedGoals.forEach((g) => {
      console.log(`  • ${g.title} (${g.status})`);
    });

    console.log('\nAgent impact:');
    const affectedAgents = new Set<string>();
    affectedGoals.forEach((g) => {
      g.assignedAgents.forEach((a) => affectedAgents.add(a));
    });
    affectedAgents.forEach((agent) => {
      console.log(`  @${agent}: Reassigned`);
    });
  }

  console.log(`\nKublai:\n${orchestrator.generateResponse(parsed)}`);
}

// ============================================================================
// Example 4: Complexity Overload Prevention
// ============================================================================

function example4_OverloadPrevention() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  console.log('=== Example 4: Complexity Overload Prevention ===\n');

  // Simulate user sending too many goals
  const tooManyGoals = [
    'Earn 1,000 USDC',
    'Start community',
    'Build lead gen',
    'Create personal brand',
    'Launch course',
    'Write book',
    'Start podcast'
  ];

  console.log(`User sends ${tooManyGoals.length} goals rapidly:`);
  tooManyGoals.forEach((g) => console.log(`  • ${g}`));

  console.log('\nKublai: ⚡ WHOA—that\'s 7 major goals!\n');
  console.log('I\'ve grouped them into 3 tracks:\n');
  console.log('⚡ TRACK 1: IMMEDIATE EARNINGS');
  console.log('   • Freelancing + Lead gen');
  console.log('   → Cash flow in 7 days\n');
  console.log('📈 TRACK 2: AUDIENCE BUILDING');
  console.log('   • Community + Brand + Podcast');
  console.log('   → Sustainable growth\n');
  console.log('💰 TRACK 3: PRODUCTS');
  console.log('   • Course + Book');
  console.log('   → Passive income\n');
  console.log('RECOMMEND: Start with Track 1, add Track 2, then Track 3');
  console.log('Trying all 7 at once = slow progress on everything\n');
  console.log('Options:');
  console.log('1. Recommended (phased approach)');
  console.log('2. All in (go big, accept slower pace)');
  console.log('3. Choose specific tracks');
  console.log('\nWhich approach?');
}

// ============================================================================
// Example 5: Transparency Modes
// ============================================================================

function example5_TransparencyModes() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  console.log('=== Example 5: Transparency Modes ===\n');

  // Simple mode (default)
  console.log('📊 SIMPLE MODE');
  console.log('─────────────────────────────────────');
  goals.forEach((goal) => {
    console.log(`🎯 ${goal.title}`);
    console.log(`   Progress: ${goal.progress}%`);
    if (goal.deadline) {
      console.log(`   Due: ${goal.deadline.toLocaleDateString()}`);
    }
  });

  // Normal mode (agent attribution)
  console.log('\n\n📊 NORMAL MODE (with agents)');
  console.log('─────────────────────────────────────');
  goals.forEach((goal) => {
    console.log(`🎯 ${goal.title}`);
    console.log(`   Progress: ${goal.progress}%`);
    console.log(`   Team: @${goal.assignedAgents.join(', @')}`);
  });

  // Detailed mode (full breakdown)
  console.log('\n\n📊 DETAILED MODE (full breakdown)');
  console.log('─────────────────────────────────────');
  goals.forEach((goal) => {
    console.log(`🎯 ${goal.title}`);
    console.log(`   Status: ${goal.status.toUpperCase()}`);
    console.log(`   Progress: ${goal.progress}%`);
    console.log(`   Priority: ${goal.priority}`);
    console.log(`   Agents: @${goal.assignedAgents.join(', @')}`);
    if (goal.synergyWith && goal.synergyWith.length > 0) {
      console.log(`   Synergies: ${goal.synergyWith.length} connection(s)`);
    }
    if (goal.deadline) {
      console.log(`   Deadline: ${goal.deadline.toLocaleDateString()}`);
    }
  });
}

// ============================================================================
// Example 6: Daily Standup
// ============================================================================

function example6_DailyStandup() {
  const goals = createSampleGoals();

  console.log('=== Example 6: Daily Standup ===\n');

  console.log('📊 DAILY STANDUP — ' + new Date().toLocaleDateString());
  console.log(''.padEnd(50, '─'));

  // Group by status
  const activeGoals = goals.filter((g) => g.status === 'active');
  const pausedGoals = goals.filter((g) => g.status === 'paused');
  const completedGoals = goals.filter((g) => g.status === 'completed');

  console.log('\n✅ COMPLETED YESTERDAY:');
  console.log('  • @mongke: Analyzed 5 freelance platforms');
  console.log('  • @ogedei: Configured Discord server');
  console.log('  • @temujin: Portfolio template 80% complete');

  console.log('\n🔄 IN PROGRESS:');
  activeGoals.forEach((goal) => {
    console.log(`  • ${goal.title}: ${goal.progress}% complete`);
  });

  console.log('\n⏸️ PAUSED:');
  pausedGoals.forEach((goal) => {
    console.log(`  • ${goal.title}`);
  });

  console.log('\n🚫 BLOCKERS: None');

  console.log('\n👀 NEEDS INPUT:');
  console.log('  • Portfolio color scheme: Blue or Purple?');
  console.log('  • Discord invite-only or open?');

  console.log('\n📝 KEY DECISIONS:');
  console.log('  • Switched to Upwork-only focus (higher rates)');
  console.log('  • Community launch delayed 2 days for better prep');

  console.log('\n🎯 TODAY\'S PRIORITIES:');
  console.log('  1. Finish portfolio template');
  console.log('  2. Send first 5 outreach emails');
  console.log('  3. Complete competitor analysis');

  console.log('\nReply "ok" to acknowledge');
  console.log('Reply "reprioritize" to change focus');
  console.log('Reply "details" for full task list');
}

// ============================================================================
// Example 7: Real Conversation Flow
// ============================================================================

function example7_RealConversation() {
  const goals = createSampleGoals();
  const orchestrator = new GoalOrchestrator(goals);

  console.log('=== Example 7: Real Conversation Flow ===\n');

  // Turn 1: User sends two goals
  console.log('User: Earn 1,000 USDC');
  console.log('User: Start money-making community\n');

  console.log('Kublai: 💡 These work together—building unified strategy');
  console.log('        Earnings fund community, community amplifies earnings\n');
  console.log('        📋 INTEGRATED PLAN:');
  console.log('        Week 1: Quick earnings (freelance sprints)');
  console.log('        Week 2: Community MVP launch');
  console.log('        Week 3: Merge (community referral program)\n');
  console.log('        Starting now. Reply "details" for full agent assignments');
  console.log('        Reply "split" to handle separately\n');

  // Turn 2: User asks for status
  console.log('─'.repeat(60));
  console.log('User: status\n');

  const statusCmd = orchestrator.parseCommand('status');
  console.log(`Kublai:\n${orchestrator.generateResponse(statusCmd)}\n`);

  // Turn 3: User wants to pause one goal
  console.log('─'.repeat(60));
  console.log('User: pause community, focus on freelancing\n');

  const pauseCmd = orchestrator.parseCommand('pause community');
  console.log(`Kublai:\n${orchestrator.generateResponse(pauseCmd)}\n`);

  // Turn 4: User confirms
  console.log('─'.repeat(60));
  console.log('User: yes\n');

  const confirmCmd = orchestrator.parseCommand('yes');
  console.log(`Kublai:\n${orchestrator.generateResponse(confirmCmd)}\n`);
}

// ============================================================================
// Run All Examples
// ============================================================================

export function runAllExamples() {
  example1_BasicParsing();
  console.log('\n\n');

  example2_SynergyDetection();
  console.log('\n\n');

  example3_MidCourseCorrection();
  console.log('\n\n');

  example4_OverloadPrevention();
  console.log('\n\n');

  example5_TransparencyModes();
  console.log('\n\n');

  example6_DailyStandup();
  console.log('\n\n');

  example7_RealConversation();
}

// Export individual examples for selective running
export {
  example1_BasicParsing,
  example2_SynergyDetection,
  example3_MidCourseCorrection,
  example4_OverloadPrevention,
  example5_TransparencyModes,
  example6_DailyStandup,
  example7_RealConversation
};
