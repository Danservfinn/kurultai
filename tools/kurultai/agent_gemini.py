#!/usr/bin/env python3
"""
Agent Gemini Manager for Kurultai

Provides each agent with their own Gemini CLI context.
All agents use Gemini 3.1 Pro Preview through separate configurations.
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass

logger = logging.getLogger("kurultai.agent_gemini")


@dataclass
class AgentGeminiConfig:
    """Configuration for an agent's Gemini CLI."""
    agent_id: str
    agent_name: str
    agent_role: str
    gemini_home: Path
    workspace: Path
    model: str = "gemini-3.1-pro-preview"


class AgentGemini:
    """
    Gemini CLI interface for a specific Kurultai agent.
    
    Each agent gets their own:
    - Configuration directory (~/.gemini-{agent})
    - Conversation history
    - Working context
    - Isolated environment
    """
    
    AGENT_ROLES = {
        "kublai": ("Squad Lead", "orchestrates tasks and manages workflow"),
        "mongke": ("Researcher", "conducts research and analysis"),
        "chagatai": ("Writer", "creates content and documentation"),
        "temujin": ("Developer", "writes code and handles technical tasks"),
        "jochi": ("Analyst", "performs data analysis and debugging"),
        "ogedei": ("Operations", "manages infrastructure and deployment")
    }
    
    def __init__(self, agent_id: str):
        """
        Initialize Gemini CLI for a specific agent.
        
        Args:
            agent_id: Agent identifier (kublai, mongke, chagatai, etc.)
        """
        if agent_id not in self.AGENT_ROLES:
            raise ValueError(f"Unknown agent: {agent_id}")
        
        self.agent_id = agent_id
        self.agent_name, self.agent_role = self.AGENT_ROLES[agent_id]
        
        # Set up paths
        self.gemini_home = Path.home() / f".gemini-{agent_id}"
        self.workspace = Path.home() / f".openclaw/agents/{agent_id}"
        
        # Ensure configuration exists
        if not self.gemini_home.exists():
            logger.warning(f"Gemini config for {agent_id} not found. Run setup first.")
    
    def query(self, prompt: str, timeout: int = 120) -> str:
        """
        Send a query to Gemini CLI for this agent.
        
        Args:
            prompt: The prompt to send
            timeout: Maximum time to wait (seconds)
        
        Returns:
            Gemini's response as string
        """
        env = os.environ.copy()
        env['GEMINI_HOME'] = str(self.gemini_home)
        env['GEMINI_AGENT'] = self.agent_id
        
        # Add agent context to prompt
        contextualized_prompt = f"""[Agent: {self.agent_name} | Role: {self.agent_role}]

{prompt}"""
        
        try:
            logger.info(f"[{self.agent_id}] Querying Gemini: {prompt[:50]}...")
            
            result = subprocess.run(
                ['gemini', '-p', contextualized_prompt],
                env=env,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                response = result.stdout.strip()
                logger.info(f"[{self.agent_id}] Got response ({len(response)} chars)")
                return response
            else:
                error_msg = f"Gemini CLI error: {result.stderr}"
                logger.error(f"[{self.agent_id}] {error_msg}")
                return f"Error: {error_msg}"
                
        except subprocess.TimeoutExpired:
            logger.error(f"[{self.agent_id}] Query timed out after {timeout}s")
            return f"Error: Query timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"[{self.agent_id}] Exception: {e}")
            return f"Error: {str(e)}"
    
    def generate_code(self, description: str, language: str = "python", 
                     context: Optional[str] = None) -> str:
        """
        Generate code using Gemini CLI.
        
        Args:
            description: What the code should do
            language: Programming language
            context: Additional context
        
        Returns:
            Generated code
        """
        prompt = f"""Generate {language} code for: {description}

Requirements:
- Follow best practices for {language}
- Include comments explaining the logic
- Make it production-ready
- Handle errors appropriately"""
        
        if context:
            prompt += f"\n\nAdditional context:\n{context}"
        
        return self.query(prompt)
    
    def analyze_code(self, code: str, task: str = "review") -> str:
        """
        Analyze code using Gemini CLI.
        
        Args:
            code: Code to analyze
            task: Type of analysis (review, debug, optimize)
        
        Returns:
            Analysis results
        """
        prompts = {
            "review": "Review this code for best practices, bugs, and improvements:",
            "debug": "Debug this code and identify issues:",
            "optimize": "Optimize this code for performance:"
        }
        
        prompt = f"""{prompts.get(task, prompts['review'])}

```
{code}
```

Provide specific recommendations and explanations."""
        
        return self.query(prompt)
    
    def research_topic(self, topic: str, depth: str = "summary") -> str:
        """
        Research a topic using Gemini CLI (Möngke's specialty).
        
        Args:
            topic: Topic to research
            depth: Depth of research (summary, detailed, comprehensive)
        
        Returns:
            Research findings
        """
        depth_instructions = {
            "summary": "Provide a concise summary of key points.",
            "detailed": "Provide detailed information with examples.",
            "comprehensive": "Provide comprehensive coverage with sources and implications."
        }
        
        prompt = f"""Research the topic: {topic}

{depth_instructions.get(depth, depth_instructions['summary'])}

Structure your response with:
1. Key findings
2. Important details
3. Practical applications"""
        
        return self.query(prompt)
    
    def write_documentation(self, subject: str, format: str = "markdown") -> str:
        """
        Write documentation using Gemini CLI (Chagatai's specialty).
        
        Args:
            subject: What to document
            format: Output format (markdown, reStructuredText, etc.)
        
        Returns:
            Documentation text
        """
        prompt = f"""Write {format} documentation for: {subject}

Include:
- Overview
- Usage examples
- Configuration options
- Best practices
- Troubleshooting"""
        
        return self.query(prompt)
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent's Gemini CLI status."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "gemini_home": str(self.gemini_home),
            "workspace": str(self.workspace),
            "configured": self.gemini_home.exists(),
            "model": "gemini-3.1-pro-preview"
        }


# Singleton manager for all agents
_agent_instances: Dict[str, AgentGemini] = {}

def get_agent_gemini(agent_id: str) -> AgentGemini:
    """
    Get or create AgentGemini instance.
    
    Args:
        agent_id: Agent identifier
    
    Returns:
        AgentGemini instance
    """
    global _agent_instances
    
    if agent_id not in _agent_instances:
        _agent_instances[agent_id] = AgentGemini(agent_id)
    
    return _agent_instances[agent_id]


# Convenience functions for each agent
def kublai_gemini() -> AgentGemini:
    """Get Kublai's Gemini instance."""
    return get_agent_gemini("kublai")

def mongke_gemini() -> AgentGemini:
    """Get Möngke's Gemini instance."""
    return get_agent_gemini("mongke")

def chagatai_gemini() -> AgentGemini:
    """Get Chagatai's Gemini instance."""
    return get_agent_gemini("chagatai")

def temujin_gemini() -> AgentGemini:
    """Get Temüjin's Gemini instance."""
    return get_agent_gemini("temujin")

def jochi_gemini() -> AgentGemini:
    """Get Jochi's Gemini instance."""
    return get_agent_gemini("jochi")

def ogedei_gemini() -> AgentGemini:
    """Get Ögedei's Gemini instance."""
    return get_agent_gemini("ogedei")


# Integration with existing agent tasks
async def agent_task_with_gemini(agent_id: str, task_type: str, **kwargs) -> str:
    """
    Execute an agent task using their dedicated Gemini CLI.
    
    This replaces the default task handler with Gemini-powered execution.
    
    Args:
        agent_id: Agent to use
        task_type: Type of task (research, code, analyze, etc.)
        **kwargs: Task-specific parameters
    
    Returns:
        Task result
    """
    agent = get_agent_gemini(agent_id)
    
    task_handlers = {
        "research": lambda: agent.research_topic(kwargs.get("topic"), kwargs.get("depth", "summary")),
        "code": lambda: agent.generate_code(
            kwargs.get("description"), 
            kwargs.get("language", "python"),
            kwargs.get("context")
        ),
        "analyze": lambda: agent.analyze_code(kwargs.get("code"), kwargs.get("task", "review")),
        "write": lambda: agent.write_documentation(kwargs.get("subject"), kwargs.get("format", "markdown")),
        "query": lambda: agent.query(kwargs.get("prompt"))
    }
    
    handler = task_handlers.get(task_type, task_handlers["query"])
    return handler()


if __name__ == "__main__":
    # Test all agents
    print("Testing Multi-Agent Gemini CLI Setup")
    print("=" * 50)
    
    agents = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]
    
    for agent_id in agents:
        agent = get_agent_gemini(agent_id)
        status = agent.get_status()
        
        print(f"\n{status['agent_name']} ({status['agent_role']}):")
        print(f"  Configured: {status['configured']}")
        print(f"  Model: {status['model']}")
        
        if status['configured']:
            # Quick test
            try:
                response = agent.query("Say 'ready' if you're operational")
                if 'ready' in response.lower() or 'Ready' in response.lower():
                    print(f"  Status: ✅ Operational")
                else:
                    print(f"  Status: ⚠️ Check manually")
            except Exception as e:
                print(f"  Status: ❌ Error - {e}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
