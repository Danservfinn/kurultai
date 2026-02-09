"""
SOUL.md Injection System for Kurultai

Parses SOUL.md files, injects learned rules at [LEARNED_RULES] section,
preserves original content, and integrates with version control.

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging
import subprocess


logger = logging.getLogger(__name__)


class InjectionStatus(Enum):
    """Status of rule injection."""
    PENDING = "pending"
    INJECTED = "injected"
    FAILED = "failed"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclass
class InjectionRecord:
    """Record of a rule injection."""
    id: str
    rule_id: str
    agent_id: str
    soul_file_path: str
    injected_at: datetime
    status: InjectionStatus
    original_content_hash: str
    injected_content: str
    git_commit_hash: Optional[str] = None
    error_message: Optional[str] = None


class SOULInjector:
    """
    Injects learned meta-rules into agent SOUL.md files.
    
    Key capabilities:
    - Parse SOUL.md files and identify injection points
    - Preserve original content while adding learned rules
    - Track injection history
    - Integrate with git for version control
    """
    
    # Marker for learned rules section
    LEARNED_RULES_START = "<!-- [LEARNED_RULES] - Auto-generated. Do not edit manually. -->"
    LEARNED_RULES_END = "<!-- [/LEARNED_RULES] -->"
    
    def __init__(self, souls_base_path: Optional[str] = None,
                 enable_git: bool = True,
                 git_auto_commit: bool = False):
        """
        Initialize the SOULInjector.
        
        Args:
            souls_base_path: Base path to agent SOUL directories
            enable_git: Whether to use git for version control
            git_auto_commit: Whether to auto-commit changes
        """
        self.souls_base_path = souls_base_path or os.environ.get(
            'SOULS_BASE_PATH', 
            '/data/workspace/souls'
        )
        self.enable_git = enable_git
        self.git_auto_commit = git_auto_commit
        
        self.injection_history: Dict[str, InjectionRecord] = {}
        
        # Verify git is available if enabled
        if self.enable_git:
            self._verify_git()
    
    def _verify_git(self) -> bool:
        """Verify git is available and we're in a repo."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                cwd=self.souls_base_path
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.warning("Git not available, disabling git integration")
            self.enable_git = False
            return False
    
    def _get_soul_file_path(self, agent_id: str) -> str:
        """Get the path to an agent's SOUL.md file."""
        # Handle different agent ID formats
        agent_dir = agent_id.lower().replace(' ', '_')
        
        # Map common agent names to directories
        agent_mapping = {
            'kublai': 'main',
            'mongke': 'researcher',
            'chagatai': 'writer',
            'temujin': 'developer',
            'jochi': 'analyst',
            'ogedei': 'ops',
        }
        
        if agent_dir in agent_mapping:
            agent_dir = agent_mapping[agent_dir]
        
        return os.path.join(self.souls_base_path, agent_dir, 'SOUL.md')
    
    def parse_soul_file(self, agent_id: str) -> Dict[str, Any]:
        """
        Parse a SOUL.md file and extract its structure.
        
        Args:
            agent_id: The agent ID
            
        Returns:
            Dict containing:
                - exists: Whether file exists
                - content: Full file content
                - sections: Dict of section names to content
                - has_learned_rules_section: Whether [LEARNED_RULES] exists
                - learned_rules_content: Content between markers (if exists)
                - injection_point: Line number for injection
        """
        file_path = self._get_soul_file_path(agent_id)
        
        result = {
            'exists': False,
            'content': '',
            'sections': {},
            'has_learned_rules_section': False,
            'learned_rules_content': '',
            'injection_point': -1,
            'file_path': file_path,
        }
        
        if not os.path.exists(file_path):
            logger.warning(f"SOUL.md not found for agent {agent_id}: {file_path}")
            return result
        
        result['exists'] = True
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result['content'] = content
        
        # Check for learned rules section
        if self.LEARNED_RULES_START in content:
            result['has_learned_rules_section'] = True
            
            # Extract content between markers
            pattern = re.escape(self.LEARNED_RULES_START) + r'(.*?)' + re.escape(self.LEARNED_RULES_END)
            match = re.search(pattern, content, re.DOTALL)
            if match:
                result['learned_rules_content'] = match.group(1).strip()
        
        # Parse sections (## headers)
        sections = {}
        current_section = 'header'
        current_content = []
        
        for line in content.split('\n'):
            if line.startswith('## '):
                # Save previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                
                # Start new section
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        result['sections'] = sections
        
        # Determine injection point
        if result['has_learned_rules_section']:
            # Find line number of existing section
            for i, line in enumerate(content.split('\n'), 1):
                if self.LEARNED_RULES_START in line:
                    result['injection_point'] = i
                    break
        else:
            # Suggest injection at end of file, before any closing
            lines = content.split('\n')
            result['injection_point'] = len(lines)
        
        return result
    
    def format_rule_for_injection(self, rule: Dict[str, Any]) -> str:
        """
        Format a meta-rule for injection into SOUL.md.
        
        Args:
            rule: Rule dict with name, description, conditions, actions, etc.
            
        Returns:
            Formatted markdown for the rule
        """
        lines = [
            f"### {rule['name']}",
            "",
            f"**Type**: {rule.get('rule_type', 'general')}",
            f"**Priority**: {rule.get('priority', 5)}/10 (lower is higher)",
            f"**Effectiveness**: {rule.get('effectiveness_score', 0):.0%}",
            "",
            f"{rule['description']}",
            "",
            "**When to apply**:",
        ]
        
        # Add conditions
        for condition in rule.get('conditions', []):
            lines.append(f"- {condition}")
        
        lines.extend(["", "**Actions**:"])
        
        # Add actions
        for action in rule.get('actions', []):
            lines.append(f"- {action}")
        
        lines.extend([
            "",
            f"*Rule ID: `{rule['id']}` | Generated: {datetime.utcnow().strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
        ])
        
        return '\n'.join(lines)
    
    def inject_rules(self, agent_id: str, 
                     rules: List[Dict[str, Any]],
                     commit_message: Optional[str] = None,
                     dry_run: bool = False) -> InjectionRecord:
        """
        Inject rules into an agent's SOUL.md file.
        
        Args:
            agent_id: The agent to inject rules for
            rules: List of rules to inject
            commit_message: Optional git commit message
            dry_run: If True, don't actually write changes
            
        Returns:
            InjectionRecord with details of the injection
        """
        file_path = self._get_soul_file_path(agent_id)
        
        # Parse existing file
        parsed = self.parse_soul_file(agent_id)
        
        if not parsed['exists']:
            error_msg = f"SOUL.md not found for agent {agent_id}"
            record = InjectionRecord(
                id=str(uuid.uuid4()),
                rule_id=','.join([r['id'] for r in rules]),
                agent_id=agent_id,
                soul_file_path=file_path,
                injected_at=datetime.utcnow(),
                status=InjectionStatus.FAILED,
                original_content_hash='',
                injected_content='',
                error_message=error_msg,
            )
            logger.error(error_msg)
            return record
        
        original_content = parsed['content']
        original_hash = self._hash_content(original_content)
        
        # Format rules for injection
        formatted_rules = [self.format_rule_for_injection(rule) for rule in rules]
        rules_content = '\n'.join(formatted_rules)
        
        # Build new content
        if parsed['has_learned_rules_section']:
            # Replace existing section
            pattern = (re.escape(self.LEARNED_RULES_START) + 
                      r'.*?' + 
                      re.escape(self.LEARNED_RULES_END))
            
            new_section = f"{self.LEARNED_RULES_START}\n\n## Learned Rules\n\n{rules_content}\n{self.LEARNED_RULES_END}"
            new_content = re.sub(pattern, new_section, original_content, flags=re.DOTALL)
        else:
            # Add new section at end
            new_section = f"\n\n{self.LEARNED_RULES_START}\n\n## Learned Rules\n\n{rules_content}\n{self.LEARNED_RULES_END}\n"
            new_content = original_content + new_section
        
        record = InjectionRecord(
            id=str(uuid.uuid4()),
            rule_id=','.join([r['id'] for r in rules]),
            agent_id=agent_id,
            soul_file_path=file_path,
            injected_at=datetime.utcnow(),
            status=InjectionStatus.PENDING,
            original_content_hash=original_hash,
            injected_content=new_content,
        )
        
        if dry_run:
            record.status = InjectionStatus.PENDING
            logger.info(f"[DRY RUN] Would inject {len(rules)} rules into {agent_id}'s SOUL.md")
            return record
        
        # Write changes
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            record.status = InjectionStatus.INJECTED
            logger.info(f"Injected {len(rules)} rules into {agent_id}'s SOUL.md")
            
            # Git operations
            if self.enable_git:
                git_hash = self._git_commit_changes(
                    file_path, 
                    agent_id, 
                    rules,
                    commit_message
                )
                record.git_commit_hash = git_hash
            
        except Exception as e:
            record.status = InjectionStatus.FAILED
            record.error_message = str(e)
            logger.error(f"Failed to inject rules for {agent_id}: {e}")
        
        self.injection_history[record.id] = record
        return record
    
    def _hash_content(self, content: str) -> str:
        """Generate a hash of content for tracking changes."""
        import hashlib
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def _git_commit_changes(self, file_path: str, 
                           agent_id: str,
                           rules: List[Dict[str, Any]],
                           custom_message: Optional[str] = None) -> Optional[str]:
        """
        Commit changes to git.
        
        Args:
            file_path: Path to modified file
            agent_id: Agent whose SOUL.md was modified
            rules: Rules that were injected
            custom_message: Optional custom commit message
            
        Returns:
            Commit hash if successful, None otherwise
        """
        if not self.enable_git:
            return None
        
        try:
            # Stage the file
            subprocess.run(
                ['git', 'add', file_path],
                check=True,
                capture_output=True,
                cwd=self.souls_base_path
            )
            
            # Create commit message
            if custom_message:
                message = custom_message
            else:
                rule_names = [r['name'] for r in rules]
                message = f"meta-learning: Inject {len(rules)} rules into {agent_id}'s SOUL.md\n\nRules:\n"
                for name in rule_names:
                    message += f"- {name}\n"
            
            # Commit
            result = subprocess.run(
                ['git', 'commit', '-m', message],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.souls_base_path
            )
            
            # Get commit hash
            hash_result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.souls_base_path
            )
            
            commit_hash = hash_result.stdout.strip()
            logger.info(f"Git commit: {commit_hash[:8]} - {agent_id} SOUL.md updated")
            return commit_hash
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git commit failed: {e.stderr}")
            return None
    
    def rollback_injection(self, injection_id: str) -> bool:
        """
        Rollback an injection by restoring original content.
        
        Args:
            injection_id: ID of the injection to rollback
            
        Returns:
            True if rollback was successful
        """
        if injection_id not in self.injection_history:
            logger.error(f"Injection record not found: {injection_id}")
            return False
        
        record = self.injection_history[injection_id]
        
        if record.status != InjectionStatus.INJECTED:
            logger.error(f"Cannot rollback injection with status: {record.status}")
            return False
        
        try:
            # Use git to revert
            if self.enable_git and record.git_commit_hash:
                subprocess.run(
                    ['git', 'revert', '--no-commit', record.git_commit_hash],
                    check=True,
                    capture_output=True,
                    cwd=self.souls_base_path
                )
                
                subprocess.run(
                    ['git', 'commit', '-m', f"Rollback meta-learning injection {injection_id[:8]}"],
                    check=True,
                    capture_output=True,
                    cwd=self.souls_base_path
                )
                
                logger.info(f"Rolled back injection {injection_id[:8]}")
                return True
            else:
                logger.error("Git not available for rollback")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Rollback failed: {e.stderr}")
            return False
    
    def get_injection_history(self, 
                             agent_id: Optional[str] = None,
                             status: Optional[InjectionStatus] = None) -> List[InjectionRecord]:
        """
        Get injection history, optionally filtered.
        
        Args:
            agent_id: Filter by agent
            status: Filter by status
            
        Returns:
            List of matching InjectionRecord objects
        """
        records = list(self.injection_history.values())
        
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        
        if status:
            records = [r for r in records if r.status == status]
        
        return sorted(records, key=lambda r: r.injected_at, reverse=True)
    
    def validate_soul_file(self, agent_id: str) -> Dict[str, Any]:
        """
        Validate a SOUL.md file structure.
        
        Args:
            agent_id: The agent to validate
            
        Returns:
            Validation results with issues found
        """
        parsed = self.parse_soul_file(agent_id)
        
        issues = []
        warnings = []
        
        if not parsed['exists']:
            issues.append("SOUL.md file does not exist")
            return {
                'valid': False,
                'issues': issues,
                'warnings': warnings,
            }
        
        content = parsed['content']
        
        # Check for required sections
        required_sections = ['Identity', 'Operational Context']
        for section in required_sections:
            if section not in parsed['sections']:
                issues.append(f"Missing required section: {section}")
        
        # Check for learned rules section issues
        if parsed['has_learned_rules_section']:
            # Verify markers are balanced
            start_count = content.count(self.LEARNED_RULES_START)
            end_count = content.count(self.LEARNED_RULES_END)
            
            if start_count != end_count:
                issues.append(f"Unbalanced learned rules markers: {start_count} start, {end_count} end")
            
            if start_count > 1:
                issues.append("Multiple learned rules sections found")
        
        # Check for common issues
        if '# SOUL.md' not in content and '# Who You Are' not in content:
            warnings.append("File may be missing title header")
        
        if len(content) < 100:
            warnings.append("SOUL.md seems very short")
        
        # Validate markdown structure
        headers = re.findall(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)
        if not headers:
            warnings.append("No markdown headers found")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'sections_found': list(parsed['sections'].keys()),
            'has_learned_rules': parsed['has_learned_rules_section'],
        }
    
    def bulk_inject(self, 
                   injection_plan: Dict[str, List[Dict[str, Any]]],
                   dry_run: bool = False) -> Dict[str, InjectionRecord]:
        """
        Inject rules for multiple agents.
        
        Args:
            injection_plan: Dict mapping agent_id to list of rules
            dry_run: If True, don't actually write changes
            
        Returns:
            Dict mapping agent_id to InjectionRecord
        """
        results = {}
        
        for agent_id, rules in injection_plan.items():
            record = self.inject_rules(agent_id, rules, dry_run=dry_run)
            results[agent_id] = record
        
        return results
    
    def sync_with_meta_learning_engine(self, engine: Any) -> Dict[str, Any]:
        """
        Sync with MetaLearningEngine to get rules and inject them.
        
        Args:
            engine: MetaLearningEngine instance
            
        Returns:
            Summary of sync operation
        """
        # Get rules for each agent
        injection_plan = engine.inject_rules(dry_run=True)
        
        results = {
            'agents_processed': 0,
            'rules_injected': 0,
            'failures': [],
            'records': {},
        }
        
        for agent_id, rule_ids in injection_plan.items():
            # Get full rule objects
            rules = [engine.rules[rid].to_dict() for rid in rule_ids if rid in engine.rules]
            
            if rules:
                record = self.inject_rules(agent_id, rules)
                results['records'][agent_id] = record
                
                if record.status == InjectionStatus.INJECTED:
                    results['agents_processed'] += 1
                    results['rules_injected'] += len(rules)
                else:
                    results['failures'].append({
                        'agent': agent_id,
                        'error': record.error_message,
                    })
        
        return results
