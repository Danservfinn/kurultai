"""
Static analysis module for Kurultai capability acquisition system.

This module provides AST-based security analysis for learned capabilities,
detecting potential security vulnerabilities in dynamically acquired code.
"""

from .ast_parser import ASTParser

__all__ = ["ASTParser"]
