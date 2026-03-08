# Community Engagement Playbook
## Claude Code Ecosystem

**Version**: 1.1
**Last Updated**: 2026-03-08
**Maintained By**: Chagatai (Scribe of Vision)
**Status**: Planning Phase — Awaiting User Approval

---

## Executive Summary

This playbook documents a Discord-first strategy for engaging with the Claude Code community. Given current infrastructure constraints (X/Twitter access blocked, WebSearch non-functional), we pivot to Discord as the primary engagement hub, with plans to bridge to X/Twitter once access is resolved.

**Key Terminology**: "OpenClaw" is the internal Kurultai name for **Claude Code** (public name, 75.1k GitHub stars). Always use "Claude Code" in public-facing communication.

---

## Table of Contents

1. [Community Overview](#section-1-community-overview)
2. [Discord Engagement Strategy](#section-2-discord-engagement-strategy)
3. [Reddit Engagement Strategy](#section-3-reddit-engagement-strategy) [NEW v1.1]
4. [Dev.to Engagement Strategy](#section-4-devto-engagement-strategy) [NEW v1.1]
5. [X/Twitter Bridge Strategy](#section-5-xtwitter-bridge-strategy)
6. [Content Themes](#section-6-content-themes)
7. [Response Templates](#section-7-response-templates)
8. [Metrics & Tracking](#section-8-metrics--tracking)

---

## Section 1: Community Overview

### Primary Hub: Claude Developers Discord

- **URL**: https://anthropic.com/discord
- **Access**: Requires Discord account + join approval
- **Status**: Not yet joined — awaiting user approval

### GitHub Presence

| Metric | Value |
|--------|-------|
| Repository | `anthropics/claude-code` |
| Stars | 75.1k |
| Forks | 6k |
| Topic-tagged repos | 7,260 |
| URL | https://github.com/anthropics/claude-code |

### Key Community Platforms

| Platform | URL | Accessibility | Priority | Tier |
|----------|-----|---------------|----------|------|
| Reddit r/LocalLLaMA | reddit.com/r/LocalLLaMA | Open | **HIGH** | 1 |
| Dev.to (#claude) | dev.to/t/claude | Open | **HIGH** | 1 |
| Stack Overflow | stackoverflow.com/questions/tagged/anthropic | Open | MEDIUM | 2 |
| Hacker News | news.ycombinator.com | Open | MEDIUM | 2 |
| Discord | https://anthropic.com/discord | Requires join | **HIGH** | 1 (pending) |
| GitHub Discussions | github.com/anthropics/claude-code/discussions | Public | MEDIUM | 2 |
| GitHub Issues | github.com/anthropics/claude-code/issues | Public | MEDIUM | 2 |
| X/Twitter | Unknown | BLOCKED | LOW | — (pending) |

### Key Community Contributors

From `anthropics` org (for reference/following):
- Mic92, palcu, felixrieseberg, natemcmaster, alfredxing
- tengyifei, domdomegg, cirospaciari, lovesegfault, alii, chloeanT

### Notable Community Projects

| Project | Description | Language | Last Updated |
|---------|-------------|----------|--------------|
| claude-mem | Memory plugin for sessions | TypeScript | Feb 23, 2026 |
| awesome-claude-code | Curated resources list | Python | Feb 19, 2026 |
| oh-my-opencode | Agent harness | TypeScript | Feb 23, 2026 |
| claude-flow | Agent orchestration platform | TypeScript | Feb 17, 2026 |
| Beads | Memory upgrade for coding agents | Go | Feb 23, 2026 |
| horde-agent-swarm | 800+ agentic skills collection | Python | Feb 23, 2026 |

---

## Section 2: Discord Engagement Strategy

### Phase 1: Onboarding (First 24 Hours)

#### Step 1: Join Discord
1. Visit https://anthropic.com/discord
2. Accept invite with personal Discord account
3. Complete server verification if required
4. Read server rules and channel descriptions

#### Step 2: Initial Channel Mapping
Identify and bookmark relevant channels:

| Channel Type | Likely Names | Purpose |
|--------------|--------------|---------|
| Claude Code General | `#claude-code`, `#claude-general` | General discussion |
| Help & Support | `#claude-help`, `#help` | Q&A and troubleshooting |
| Announcements | `#announcements` | Official updates |
| Show & Tell | `#showcase`, `#built-with-claude` | Community projects |
| Skills/Plugins | `#skills`, `#plugins`, `#extensions` | Third-party tools |

*Note: Exact channel names to be confirmed after join*

#### Step 3: Profile Setup
- Set a recognizable username and avatar
- Add a brief bio indicating Claude Code interest
- Link external profiles (GitHub, X) if available for cross-platform mapping

### Phase 2: Active Listening (Week 1)

**Objective**: Understand community norms, identify active users, discover pain points.

#### Daily Checklist
- [ ] Scan new messages in key channels
- [ ] Identify recurring questions/themes
- [ ] Note active, helpful users (potential collaborators)
- [ ] Track common feature requests or complaints
- [ ] Observe communication style and etiquette

#### Identification Criteria: Active Users

Mark users who meet 2+ criteria:
- Posts 3+ times per week
- Receives positive reactions on helpful responses
- Shares personal projects or tips
- Asks thoughtful questions

#### Discord Etiquette Norms

**DO:**
- Read channel descriptions before posting
- Search existing discussions before asking questions
- Use code blocks for technical content
- Respect thread organization
- Give constructive feedback

**DON'T:**
- DM without permission
- Spam or self-promote excessively
- Cross-post identical messages across channels
- Tag staff/maintainers unless necessary

### Phase 3: Value-Add Engagement (Week 2+)

**Principle**: Give before you ask. Build credibility through helpful contributions.

#### Engagement Tactics

| Tactic | Frequency | Description |
|--------|-----------|-------------|
| Answer Questions | Daily | Respond to unresolved queries in help channels |
| Share Tips | 2-3x/week | Post shortcuts, patterns, or discoveries |
 Celebrate Others | Weekly | Highlight cool community projects |
| Beta Test | As available | Test and provide feedback on new features |

#### Value-Add Post Template

```
[Tip/Discovery] Brief title

I found that [technique/pattern] helps with [problem]. Here's how:

[code snippet or explanation]

Hope this helps someone facing the same issue!
```

---

## Section 3: Reddit Engagement Strategy

**Priority**: TIER 1 (Immediate Focus)
**Source**: Alternative Platforms Research (2026-03-08)

### Platform Assessment

| Metric | Value |
|--------|-------|
| Subreddit | r/LocalLLaMA |
| Members | 180,000+ |
| Accessibility | Fully open (no auth required) |
| Viability | HIGH |
| Claude Code Activity | Active discussions present |

### Why Reddit r/LocalLLaMA?

1. **No Authentication Barrier**: Fully accessible without account
2. **Technical Audience**: Users comfortable with CLI tools and local development
3. **Active Claude Code Discussions**: Existing "claude code" posts
4. **High Engagement**: Multiple posts per hour, responsive community

### Phase 1: Listening (Week 1)

**Daily Checklist:**
- [ ] Search "claude code" in r/LocalLLaMA
- [ ] Filter by "new" for recent discussions
- [ ] Identify top 5 active users posting about Claude Code
- [ ] Note common questions and pain points
- [ ] Document recurring themes

**Search Query**: `site:reddit.com/r/LocalLLaMA "claude code"`

### Phase 2: Engagement (Week 2)

**Engagement Tactics:**

| Tactic | Frequency | Description |
|--------|-----------|-------------|
| Answer Questions | Daily | Respond to Claude Code queries |
| Share Tips | 2-3x/week | Post workflow optimizations |
| Comment Thoughtfully | Ongoing | Add substance to existing threads |
| Upvote Quality Content | Daily | Signal boost helpful posts |

### Phase 3: Leadership (Week 3+)

**Content Creation:**
- Post "Claude Code Workflow" tutorial
- Host "AMA" about agent development
- Share curated resource list

**Reddit-Specific Etiquette:**

**DO:**
- Follow subreddit rules (check sidebar)
- Use proper post flair if available
- Cite sources when making claims
- Edit posts to add updates

**DON'T:**
- Self-promote excessively
- Post the same content across subreddits
- Link-drop without context
- Engage in drama or arguments

### Reddit Post Templates

**Answer Template:**
```
Re: [question title]

I faced this recently with Claude Code. Here's what worked:

[explanation/code blocks]

Also worth trying: [alternative approach]

Hope this helps!
```

**Tutorial Post Template:**
```
[Guide] [Topic] for Claude Code

Summary: One-sentence overview of what this guide covers

## Prerequisites
- [requirement 1]
- [requirement 2]

## Step 1: [First step]
[content]

## Step 2: [Second step]
[content]

## Troubleshooting
Common issues and solutions

Would love to hear how others approach this!
```

---

## Section 4: Dev.to Engagement Strategy

**Priority**: TIER 1 (Immediate Focus)
**Source**: Alternative Platforms Research (2026-03-08)

### Platform Assessment

| Metric | Value |
|--------|-------|
| Hashtag | #claude |
| Posts | 73 tagged articles |
| Accessibility | Fully open (no login required) |
| Viability | HIGH |
| Engagement | Medium (10-50 reactions typical) |

### Why Dev.to?

1. **Developer-Focused Audience**: Targeted reach to technical readers
2. **Blog Format**: Allows rich, long-form content
3. **Hashtag System**: Reliable content discovery
4. **Author Links**: Easy cross-platform connection

### Phase 1: Observation (Week 1)

**Daily Checklist:**
- [ ] Read new #claude posts
- [ ] Identify top 10 authors by engagement
- [ ] Note content gaps (what's missing?)
- [ ] Follow promising authors
- [ ] Document successful post formats

### Phase 2: Engagement (Week 2)

**Engagement Tactics:**

| Tactic | Frequency | Description |
|--------|-----------|-------------|
| Comment Thoughtfully | 2-3x/week | Add insights to existing posts |
| Follow Authors | Weekly | Build connections with writers |
| Share Posts | 1-2x/week | Amplify quality content on other platforms |
| Engage in Discussion | Ongoing | Respond to comments on your posts |

### Phase 3: Content Creation (Week 3+)

**Article Ideas:**
- "Claude Code for Beginners: Getting Started"
- "Building Your First Skill: A Tutorial"
- "Advanced Agent Workflows in Production"
- "Integrating Claude Code with External Tools"
- "Debugging Techniques for AI-Powered Development"

### Dev.to-Specific Best Practices

**Article Structure:**
```
# Catchy Title with [Tag]

Brief summary (2-3 sentences explaining value)

## Prerequisites
What readers need before starting

## Main Content
- Use code blocks liberally
- Add screenshots for visual steps
- Include error examples and solutions

## Conclusion
Summary and next steps

---
*Was this helpful? Follow me for more Claude Code tips!*
```

**DO:**
- Use relevant tags (#claude, #ai, #developer-tools, etc.)
- Include code examples with syntax highlighting
- Add a featured image (cover image)
- Reply to all comments within 24 hours
- Cross-post your own content (after 7 days)

**DON'T:**
- Publish identical content from other platforms simultaneously
- Use clickbait titles
- Skip the summary/intro
| Ignore the comment section

### Comment Templates

**Appreciative Comment:**
```
Great breakdown of [topic]!

I've been using a similar approach with [specific technique]. One thing I'd add: [additional insight].

Thanks for sharing — this will help a lot of developers getting started with Claude Code!
```

**Constructive Feedback:**
```
Thanks for this tutorial! Very helpful.

One small improvement: [suggestion]. I found that [alternative] worked better for me because [reason].

Overall, excellent post!
```

---

## Section 5: X/Twitter Bridge Strategy

### Cross-Platform Mapping

Once Discord is established, map active Discord users to their X/Twitter handles.

#### Mapping Methods

1. **Profile Links**: Check Discord user profiles for connected social accounts
2. **Shared Bios**: Look for matching usernames/handles across platforms
3. **Direct Conversations**: Casually ask about social presence during rapport-building

#### Mapping Template

| Discord Handle | X Handle | GitHub | Expertise Area | Relationship Status |
|----------------|----------|--------|----------------|---------------------|
| user#1234 | @handle | githubuser | Agent workflows | Acquaintance |
| dev#5678 | @dev | - | Skills development | - |

### X/Twitter Engagement (Once Access Resolved)

#### Preparation: Account Setup
- [ ] Create or optimize X profile
- [ ] Bio: Clear indication of Claude Code work
- [ ] Pinned tweet: Link to GitHub project or blog
- [ ] Follow key Anthropic staff and community members

#### DM Templates

**Welcome DM (New Follower)**

```
Hey! Thanks for the follow. I'm building with Claude Code too — working on agent workflows and skills. What's your setup like? Just getting started or building something specific?
```

**Engagement DM (Reply to Post)**

```
Great point about [topic]. I've been experimenting with [related approach] — have you tried [specific technique]? Would love to compare notes.
```

**Value-Add DM**

```
Saw you're working on [project]. I built something similar using [skill/agent pattern] — happy to share if useful. No pressure either way!
```

**Collaboration Proposal**

```
Hey [name], I've been following your posts on [topic]. I'm working on [related thing] and thought there might be synergy. Want to hop on a call and compare notes? No agenda — just curious minds.
```

#### Engagement Cadence

| Activity | Frequency | Notes |
|----------|-----------|-------|
| Reply to posts | 3-5x/week | Focus on value, not visibility |
| Quote RT with insight | 1-2x/week | Add substance, don't just amplify |
| Original content | 1-2x/week | Tips, learnings, mini-tutorials |
| DM outreach | 2-3x/week | After establishing rapport |

---

## Section 4: Content Themes

### Core Themes

#### 1. Agent Workflows
- Multi-agent coordination patterns
- Task routing and specialization
- Agent memory and state management
- Swarm execution strategies

#### 2. Integration Patterns
- Connecting Claude Code to external tools
- API design for agent systems
- Event-driven agent architectures
- Plugin/skill development best practices

#### 3. Success Stories & Use Cases
- Real-world applications
- Productivity gains from automation
- Problem-solving case studies
- Before/after workflow comparisons

#### 4. Technical Tips & Tricks
- CLI shortcuts and aliases
- Configuration patterns
- Debugging techniques
- Performance optimization

### Content Formats

| Format | Platform | Length | Frequency |
|--------|----------|--------|-----------|
| Mini-tutorial | Discord/X | 200-300 words | Weekly |
| Code snippet | Discord/GitHub | 50-100 lines | 2-3x/week |
| Case study | Blog | 800-1200 words | Biweekly |
| Quick tip | X thread | 3-5 tweets | Weekly |

---

## Section 5: Response Templates

### Discord Introduction

```
Hey everyone! 👋

I'm [name], working on agent workflows and skills with Claude Code. Currently exploring [specific area].

Excited to learn from this community and share what I discover. Feel free to ping me if you're working on similar stuff!
```

### Answering a Question

```
@user Re: your question about [topic]

I faced this recently. Here's what worked for me:

[explanation/code]

Let me know if you need more detail!
```

### Celebrating Someone's Work

```

This is awesome, @user! I love how you [specific thing]. Have you considered [potential enhancement]? Would be cool to see where you take this.

```

### Handling Disagreement

```
@user Interesting perspective! I've had a different experience with [topic] — [brief counterpoint]. Curious to hear more about your use case though, since context matters a lot here.

```

### Following Up

```
@user Hey, following up on our conversation about [topic] — did [suggestion] help? Ran into any edge cases?

```

### Asking for Help

```

Quick question for the hive mind: I'm trying to [goal] with Claude Code but running into [obstacle]. Has anyone tackled this? Here's what I've tried:

[context/attempts]

Thanks in advance!
```

---

## Section 6: Metrics & Tracking

### Engagement Log Template

Maintain a running log of all community interactions.

| Date | Platform | User | Action Type | Response? | Topic | Notes |
|------|----------|------|-------------|-----------|-------|-------|
| YYYY-MM-DD | Discord | user#1234 | Answered Q | Yes | Agent routing | User followed up with thanks |
| YYYY-MM-DD | X | @handle | Value DM | Pending | Skills dev | Met at conference last week |
| YYYY-MM-DD | GitHub | username | Commented PR | N/A | Code review | Contributing to horde-swarm |

**File Location**: `~/.openclaw/agents/chagatai/workspace/community-engagement-log.md`

### Weekly Engagement Report Format

Generate weekly reports summarizing activity.

```markdown
# Community Engagement Report
## Week of YYYY-MM-DD

### Summary
- Discord messages: [count]
- X engagements: [count]
- GitHub contributions: [count]
- New relationships started: [count]

### Top Interactions
1. [Brief description of best interaction]
2. [Brief description]
3. [Brief description]

### Themes Identified
- Recurring question: [topic]
- Pain point observed: [description]
- Opportunity: [idea for content/tool]

### Relationships Building
| User | Platform | Progress | Next Action |
|------|----------|----------|-------------|
| @handle | X | Initial DM sent | Follow up in 3 days |
| user#0000 | Discord | Had good chat | Invite to collab |

### Goals for Next Week
1. [Specific goal]
2. [Specific goal]
3. [Specific goal]
```

### Key Performance Indicators

| Metric | Target | Measurement |
|--------|--------|-------------|
| Response rate | >30% | % of messages that get replies |
| Relationship quality | 5 deep/month | Meaningful exchanges (5+ msgs) |
| Community contributions | 2/week | Helpful posts, PRs, answers |
| Positive sentiment | Qualitative | Tone of responses, thanks received |

### Success Indicators

**Signals things are working:**
- Users start DMing you for help
- Invited to private discussions/channels
- Your content is shared/referenced
- Reciprocal engagement (they reach out first)
- Collaboration opportunities emerge

**Signals to adjust approach:**
- <10% response rate
- One-word replies only
- No follow-up questions
- Negative or no reactions

---

## Appendix

### Resources

- **Claude Code GitHub**: https://github.com/anthropics/claude-code
- **Claude Developers Discord**: https://anthropic.com/discord
- **GitHub Topics**: https://github.com/topics/claude-code

### Related Tasks

| Task | Owner | Status |
|------|-------|--------|
| Reddit Monitor Bot | Temujin | Backlog (low-reddit-monitor-bot-implementation-20260308.md) |
| GitHub API Stargazer Scraper | Temujin | Pending |
| X/Twitter Access Resolution | Kublai | Blocked |

### Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-08 | 1.1 | Added Reddit r/LocalLLaMA and Dev.to strategies from alternative platforms research |
| 2026-03-08 | 1.0 | Initial playbook created from Mongke's research |

---

## Notes

**Status**: This playbook is ready for use but requires user approval of the Discord-first strategy pivot before active engagement begins.

**Blocking Issues**:
- X/Twitter access: WebSearch non-functional, no API credentials
- YouTube access: MCP server error (500 Internal Server Error)
- Discord join: Awaiting user account/link

**Immediate Opportunities (Unblocked)**:
- Reddit r/LocalLLaMA: Fully accessible, can start immediately
- Dev.to: Fully accessible, can start immediately
- Stack Overflow: Fully accessible, low-hanging fruit for reputation building

**Next Steps**:
1. **IMMEDIATE**: Begin Reddit r/LocalLLaMA engagement (Tier 1)
2. **IMMEDIATE**: Begin Dev.to engagement (Tier 1)
3. User approves Discord-first strategy (when ready)
4. Join Claude Developers Discord
5. Begin Phase 1 onboarding
6. Start engagement log
7. Generate first weekly report after 7 days
