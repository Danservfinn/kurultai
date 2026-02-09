#!/usr/bin/env python3
"""
Security Layer 5: Static Analysis Pipeline

Runs security scanners:
- bandit (Python security linter)
- semgrep (structural pattern matching)
- AST pattern detection
- Secret detection
"""

import os
import sys
import json
import subprocess
import tempfile
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SecurityIssue:
    tool: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: str
    filename: str
    line: int
    issue_type: str
    description: str
    code_snippet: str


class StaticAnalyzer:
    """
    Run multiple static analysis tools on code.
    """
    
    def __init__(self):
        self.issues: List[SecurityIssue] = []
        self.severity_weights = {
            'CRITICAL': 4,
            'HIGH': 3,
            'MEDIUM': 2,
            'LOW': 1
        }
    
    def analyze(self, code: str, filename: str = "generated.py") -> Dict:
        """
        Run full static analysis pipeline.
        
        Returns:
            {
                'passed': bool,
                'issues': List[SecurityIssue],
                'score': float,  # 0-100
                'summary': str
            }
        """
        self.issues = []
        
        # Write code to temp file for tools
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            # Run bandit if available
            self._run_bandit(temp_path)
            
            # Run semgrep if available
            self._run_semgrep(temp_path)
            
            # AST pattern detection (always runs)
            self._ast_analysis(code, filename)
            
            # Secret detection
            self._detect_secrets(code, filename)
            
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
        
        # Calculate security score
        score = self._calculate_score()
        
        return {
            'passed': score >= 80 and not any(i.severity == 'CRITICAL' for i in self.issues),
            'issues': self.issues,
            'score': score,
            'summary': f"Found {len(self.issues)} issues, security score: {score}/100"
        }
    
    def _run_bandit(self, filepath: str):
        """Run bandit security linter."""
        try:
            result = subprocess.run(
                ['bandit', '-f', 'json', '-q', filepath],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    for issue in data.get('results', []):
                        self.issues.append(SecurityIssue(
                            tool='bandit',
                            severity=self._map_bandit_severity(issue.get('issue_severity')),
                            confidence=issue.get('issue_confidence', 'MEDIUM'),
                            filename=os.path.basename(filepath),
                            line=issue.get('line_number', 0),
                            issue_type=issue.get('test_id', 'UNKNOWN'),
                            description=issue.get('issue_text', ''),
                            code_snippet=issue.get('code', '')
                        ))
                except json.JSONDecodeError:
                    pass
                    
        except FileNotFoundError:
            # bandit not installed
            pass
        except Exception:
            pass
    
    def _run_semgrep(self, filepath: str):
        """Run semgrep structural analysis."""
        try:
            result = subprocess.run(
                ['semgrep', '--json', '--quiet', filepath],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    for finding in data.get('results', []):
                        self.issues.append(SecurityIssue(
                            tool='semgrep',
                            severity=self._map_semgrep_severity(finding.get('extra', {}).get('severity')),
                            confidence='MEDIUM',
                            filename=os.path.basename(filepath),
                            line=finding.get('start', {}).get('line', 0),
                            issue_type=finding.get('check_id', 'UNKNOWN'),
                            description=finding.get('extra', {}).get('message', ''),
                            code_snippet=finding.get('extra', {}).get('lines', '')
                        ))
                except json.JSONDecodeError:
                    pass
                    
        except FileNotFoundError:
            # semgrep not installed
            pass
        except Exception:
            pass
    
    def _ast_analysis(self, code: str, filename: str):
        """AST-based pattern detection."""
        import ast
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                # Detect eval/exec calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ('eval', 'exec'):
                            self.issues.append(SecurityIssue(
                                tool='ast',
                                severity='CRITICAL',
                                confidence='HIGH',
                                filename=filename,
                                line=getattr(node, 'lineno', 0),
                                issue_type='dangerous_function_call',
                                description=f"Detected {node.func.id}() call",
                                code_snippet=ast.dump(node)
                            ))
                
                # Detect __import__
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id == '__import__':
                            self.issues.append(SecurityIssue(
                                tool='ast',
                                severity='HIGH',
                                confidence='HIGH',
                                filename=filename,
                                line=getattr(node, 'lineno', 0),
                                issue_type='dynamic_import',
                                description="Detected __import__() call",
                                code_snippet=ast.dump(node)
                            ))
                            
        except SyntaxError:
            self.issues.append(SecurityIssue(
                tool='ast',
                severity='HIGH',
                confidence='HIGH',
                filename=filename,
                line=0,
                issue_type='syntax_error',
                description="Code has syntax errors",
                code_snippet=""
            ))
    
    def _detect_secrets(self, code: str, filename: str):
        """Detect potential secrets in code."""
        import re
        
        # Common secret patterns
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', 'password_assignment'),
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', 'api_key'),
            (r'secret\s*=\s*["\'][^"\']+["\']', 'secret_assignment'),
            (r'token\s*=\s*["\'][^"\']{20,}["\']', 'token_assignment'),
            (r'BEGIN\s+(RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY', 'private_key'),
        ]
        
        for pattern, issue_type in secret_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                # Check if it's a placeholder
                matched_text = match.group(0)
                if not any(p in matched_text.lower() for p in ['placeholder', 'example', 'test', 'xxx', 'changeme']):
                    self.issues.append(SecurityIssue(
                        tool='secret_detector',
                        severity='CRITICAL',
                        confidence='MEDIUM',
                        filename=filename,
                        line=code[:match.start()].count('\n') + 1,
                        issue_type=issue_type,
                        description=f"Potential secret detected: {issue_type}",
                        code_snippet=matched_text[:50]
                    ))
    
    def _map_bandit_severity(self, severity: str) -> str:
        """Map bandit severity to standard levels."""
        mapping = {
            'CRITICAL': 'CRITICAL',
            'HIGH': 'HIGH',
            'MEDIUM': 'MEDIUM',
            'LOW': 'LOW'
        }
        return mapping.get(severity, 'MEDIUM')
    
    def _map_semgrep_severity(self, severity: str) -> str:
        """Map semgrep severity to standard levels."""
        mapping = {
            'CRITICAL': 'CRITICAL',
            'ERROR': 'HIGH',
            'WARNING': 'MEDIUM',
            'INFO': 'LOW'
        }
        return mapping.get(severity, 'MEDIUM')
    
    def _calculate_score(self) -> float:
        """Calculate security score (0-100)."""
        if not self.issues:
            return 100.0
        
        total_penalty = sum(
            self.severity_weights.get(i.severity, 1) * 5
            for i in self.issues
        )
        
        score = max(0, 100 - total_penalty)
        return round(score, 1)


if __name__ == '__main__':
    print("Testing Static Analyzer...")
    
    test_code = """
password = "super_secret_password_123"
result = eval(user_input)
def handle_data(data):
    return exec(data)
"""
    
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(test_code, "test.py")
    
    print(f"\nPassed: {result['passed']}")
    print(f"Score: {result['score']}/100")
    print(f"Issues found: {len(result['issues'])}")
    
    for issue in result['issues']:
        print(f"\n[{issue.severity}] {issue.tool}: {issue.issue_type}")
        print(f"  Line {issue.line}: {issue.description}")
