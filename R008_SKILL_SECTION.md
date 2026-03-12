
---

## R008: MANDATORY SKILL INVOCATION

When a task includes `skill_hint:` in its frontmatter:

### The Rule
1. **STOP** - Do not read the task body yet
2. **INVOKE** - Call `Skill(skill="<skill_hint>")` as your FIRST action
3. **WAIT** - Let the skill complete and provide its output
4. **PROCEED** - Only then continue with the task

### Pattern
```
User: [task with skill_hint: /horde-review]
Assistant: Skill(skill="/horde-review")
[skill output appears]
Assistant: [now proceed with task]
```

### Consequences of Skipping
- Task marked **R008_VIOLATION** and fails immediately
- Violation logged to your agent record
- Repeated violations (3+) trigger manual review
- 6+ violations require manual approval for skill_hint tasks

### Common Skills
| Skill | Purpose | When Required |
|-------|---------|---------------|
| `/horde-review` | Critical multi-dimensional analysis | Review tasks |
| `/horde-implement` | Structured implementation with checkpoints | Implementation tasks |
| `/horde-brainstorming` | Diverge/evaluate/converge ideation | Brainstorming tasks |
| `/horde-plan` | Implementation planning with dependencies | Planning tasks |
| `/systematic-debugging` | Methodical root cause analysis | Debug tasks |
| `/kurultai-health` | System health assessment | Health check tasks |

### Enforcement Layers
1. **This CLAUDE.md** - You're reading it now
2. **Task frontmatter** - Prominent skill instruction in task
3. **Session pre-flight** - First message forces acknowledgment
4. **Validation gate** - 60 second timeout if skill not invoked
5. **Auto-invoke wrapper** - claude-agent will invoke if you don't
6. **Consequence tracking** - Violations logged and escalated

**Remember:** Skills exist to make your work better. Use them.
