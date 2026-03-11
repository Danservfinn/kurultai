#!/usr/bin/env python3
"""
Prompt Optimizer - Integrates horde-prompt for task optimization.

Analyzes task descriptions and optimizes them before sending to Claude Code.
Uses horde-prompt for intelligent prompt engineering with caching.
"""

import os
import sys
import json
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

# Add horde-prompt to path
SKILLS_DIR = os.path.expanduser("~/.claude/skills")
HORDE_PROMPT_DIR = os.path.join(SKILLS_DIR, "horde-prompt")
if HORDE_PROMPT_DIR not in sys.path:
    sys.path.insert(0, HORDE_PROMPT_DIR)

from prompt_cache import get_cache, CacheEntry


# Default configuration
DEFAULT_CONFIG = {
    "enabled": True,
    "cache_enabled": True,
    "cache_ttl_seconds": 3600,
    "fallback_to_original": True,
    "model_for_optimization": "claude-haiku-4-5-20251001",
    "token_budget": "standard",
    "min_task_length": 50,  # Only optimize tasks longer than this
    "skip_skill_hints": ["systematic-debugging", "horde-debug", "verification"],  # Skip optimization for these skills
}


@dataclass
class OptimizationResult:
    """Result from prompt optimization."""
    optimized: bool
    prompt: str
    original_task: str
    agent_type: str
    cached: bool
    metadata: Dict[str, Any]
    error: Optional[str] = None


def load_optimizer_config() -> Dict[str, Any]:
    """Load optimizer configuration from settings file."""
    config_path = os.path.expanduser("~/.openclaw/config/prompt-optimizer.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
            # Merge with defaults
            return {**DEFAULT_CONFIG, **user_config}
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def should_optimize(
    task: str,
    agent_type: str,
    skill_hint: Optional[str],
    config: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Determine if a task should be optimized.

    Returns (should_optimize, reason).
    """
    if not config.get("enabled", True):
        return False, "disabled"

    # Skip short tasks
    if len(task) < config.get("min_task_length", 50):
        return False, "task_too_short"

    # Skip tasks with certain skill hints
    skip_skills = config.get("skip_skill_hints", [])
    if skill_hint and skill_hint in skip_skills:
        return False, f"skill_hint_{skill_hint}"

    return True, "eligible"


def detect_agent_type(agent_name: str, task: str, skill_hint: Optional[str]) -> str:
    """
    Detect the appropriate horde-prompt agent type.

    Maps Kurultai agent names and task context to horde-prompt agent types.
    """
    # Direct mapping from Kurultai agent names
    agent_mapping = {
        "temujin": "backend-architect",  # Developer
        "jochi": "code-reviewer",  # Reviewer
        "ogedei": "senior-devops",  # Deployer
        "tolui": "senior-data-engineer",  # Data specialist
        "chagatai": "frontend-developer",  # Frontend specialist
        "mongke": "cost-analyst",  # Coordinator/Cost analyst
        "kublai": "general-purpose",  # CEO - general
    }

    if agent_name in agent_mapping:
        return agent_mapping[agent_name]

    # Try to detect from skill hint
    if skill_hint:
        skill_to_agent = {
            "senior-backend": "backend-architect",
            "senior-frontend": "frontend-developer",
            "senior-devops": "senior-devops",
            "code-reviewer": "code-reviewer",
            "horde-review": "code-reviewer",
            "horde-debug": "general-purpose",
            "systematic-debugging": "general-purpose",
            "data-scientist": "data-scientist",
            "senior-data-engineer": "senior-data-engineer",
        }
        for skill_prefix, agent_type in skill_to_agent.items():
            if skill_hint.startswith(skill_prefix):
                return agent_type

    # Default to general-purpose
    return "general-purpose"


def optimize_prompt(
    task: str,
    agent_name: str,
    skill_hint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None
) -> OptimizationResult:
    """
    Optimize a task prompt using horde-prompt.

    Args:
        task: Original task description
        agent_name: Name of the agent (temujin, jochi, etc.)
        skill_hint: Optional skill that will be invoked
        context: Additional context for optimization
        config: Optional config override

    Returns:
        OptimizationResult with optimized prompt or original on failure
    """
    config = config or load_optimizer_config()
    cache = get_cache() if config.get("cache_enabled", True) else None

    # Detect agent type
    agent_type = detect_agent_type(agent_name, task, skill_hint)

    # Check if we should optimize
    should, reason = should_optimize(task, agent_type, skill_hint, config)
    if not should:
        return OptimizationResult(
            optimized=False,
            prompt=task,
            original_task=task,
            agent_type=agent_type,
            cached=False,
            metadata={"reason": reason}
        )

    # Check cache
    if cache:
        cached = cache.get(task, agent_type, context)
        if cached:
            return OptimizationResult(
                optimized=True,
                prompt=cached.optimized_prompt,
                original_task=task,
                agent_type=agent_type,
                cached=True,
                metadata=cached.metadata
            )

    # Perform optimization
    start_time = time.time()
    try:
        from prompts import generate_prompt, PromptResult

        result: PromptResult = generate_prompt(
            task=task,
            agent_type=agent_type,
            context=context,
            token_budget=config.get("token_budget", "standard"),
        )

        optimized_prompt = result.prompt
        metadata = {
            "estimated_tokens": result.estimated_tokens,
            "compression_ratio": result.compression_ratio,
            "agent_tier": result.agent_tier,
            "confidence": result.confidence,
            "optimizations_applied": result.optimizations_applied,
            "optimization_time_ms": int((time.time() - start_time) * 1000),
        }

        # Cache the result
        if cache:
            cache.set(
                task=task,
                agent_type=agent_type,
                optimized_prompt=optimized_prompt,
                metadata=metadata,
                context=context,
                ttl_seconds=config.get("cache_ttl_seconds", 3600)
            )

        return OptimizationResult(
            optimized=True,
            prompt=optimized_prompt,
            original_task=task,
            agent_type=agent_type,
            cached=False,
            metadata=metadata
        )

    except Exception as e:
        # Fallback to original prompt
        if config.get("fallback_to_original", True):
            return OptimizationResult(
                optimized=False,
                prompt=task,
                original_task=task,
                agent_type=agent_type,
                cached=False,
                metadata={"error": str(e), "fallback": True},
                error=str(e)
            )
        raise


def enhance_task_prompt(
    task: str,
    agent_name: str,
    memory: Optional[str] = None,
    skill_hint: Optional[str] = None,
    context_history: Optional[str] = None,
    audience: Optional[str] = None,
    rules: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Enhance a full task prompt for Claude Code execution.

    This is the main entry point called by agent-task-handler.py.
    It optimizes the core task description while preserving the
    context sections (memory, skill hint, rules, etc.).

    Args:
        task: The core task description
        agent_name: Agent name (temujin, jochi, etc.)
        memory: Agent memory section (already formatted)
        skill_hint: Skill to invoke
        context_history: Cross-agent context (already formatted)
        audience: Audience hint
        rules: Behavioral rules section (already formatted)

    Returns:
        Tuple of (enhanced_prompt, metadata_dict)
    """
    config = load_optimizer_config()

    # Build context for optimization
    opt_context = {}
    if skill_hint:
        opt_context["skill_hint"] = skill_hint
    if audience:
        opt_context["audience"] = audience

    # Optimize the core task
    result = optimize_prompt(
        task=task,
        agent_name=agent_name,
        skill_hint=skill_hint,
        context=opt_context,
        config=config
    )

    # Build the full prompt with optimized task
    prompt_parts = []

    # R008 FIX: Skill hint as MANDATORY FIRST ACTION (not just a suggestion at the end)
    # This ensures agents cannot miss the skill requirement
    if skill_hint:
        skill_name = skill_hint.lstrip('/')
        prompt_parts.append(f"""
⚠️ ═══════════════════════════════════════════════════════════════════════════════
🚨 R008 RULE ENFORCEMENT: MANDATORY SKILL INVOCATION
══════════════════════════════════════════════════════════════════════════════ ⚠️

This task REQUIRES you to invoke the {skill_hint} skill.

YOUR FIRST ACTION MUST BE:
    Skill(skill="{skill_name}")

DO NOT:
- Skip this step
- Do other work first
- Only reference the skill without invoking it

If you do not invoke this skill, your task will be marked as FAILED with R008_VIOLATION.

═════════════════════════════════════════════════════════════════════════════════

""")

    # Context history (cross-agent clarity)
    if context_history:
        prompt_parts.append(context_history)

    # Optimized (or original) task
    prompt_parts.append(result.prompt)

    # Memory section
    if memory:
        prompt_parts.append(f"\n\n## Recent Context\n{memory}")

    # Audience section
    if audience:
        if audience == 'human':
            prompt_parts.append("\n\n**Output Format:** This task's output is intended for human review. Prioritize clarity, include summaries, and use markdown formatting.")
        elif audience == 'both':
            prompt_parts.append("\n\n**Output Format:** This task's output is for both agent and human consumption. Include a clear summary section and detailed technical content.")

    # Rules section
    if rules:
        prompt_parts.append(rules)

    # Execution instruction
    prompt_parts.append("\n\nExecute this task completely using your tools. Read files, write code, run commands, verify your work. For simple questions, a direct answer is fine.")

    enhanced_prompt = "".join(prompt_parts)

    metadata = {
        "optimized": result.optimized,
        "cached": result.cached,
        "agent_type": result.agent_type,
        **result.metadata
    }

    if result.error:
        metadata["optimization_error"] = result.error

    return enhanced_prompt, metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prompt optimization CLI")
    parser.add_argument("task", help="Task to optimize")
    parser.add_argument("--agent", default="temujin", help="Agent name")
    parser.add_argument("--skill", help="Skill hint")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    parser.add_argument("--stats", action="store_true", help="Show cache stats")

    args = parser.parse_args()

    if args.stats:
        cache = get_cache()
        print(json.dumps(cache.stats(), indent=2))
        exit(0)

    config = load_optimizer_config()
    if args.no_cache:
        config["cache_enabled"] = False

    result = optimize_prompt(
        task=args.task,
        agent_name=args.agent,
        skill_hint=args.skill,
        config=config
    )

    output = {
        "optimized": result.optimized,
        "cached": result.cached,
        "agent_type": result.agent_type,
        "prompt": result.prompt,
        "metadata": result.metadata
    }
    if result.error:
        output["error"] = result.error

    print(json.dumps(output, indent=2))
