"""Adaptive learning system for AI-generated code fixes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class FixAttempt:
    """Record of a fix attempt."""
    code_hash: str
    code_snippet: str
    quality_before: float
    quality_after: float
    quality_delta: float
    issues: List[str]
    success: bool
    timestamp: str
    pattern: Optional[str] = None  # Extracted pattern (e.g., "font_size_adjustment")


class AdaptiveLearningSystem:
    """Learn from fix attempts and improve over time."""
    
    def __init__(self, knowledge_base_path: Optional[Path] = None):
        """Initialize learning system.
        
        Args:
            knowledge_base_path: Path to save/load knowledge base (optional)
        """
        self.kb_path = knowledge_base_path
        self.knowledge_base = {
            'successful_fixes': [],
            'failed_fixes': [],
            'patterns': {},  # pattern_name -> {success_count, total_count, success_rate}
            'last_updated': None
        }
        
        if self.kb_path and self.kb_path.exists():
            self._load_knowledge_base()
    
    def _load_knowledge_base(self):
        """Load knowledge base from disk."""
        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.knowledge_base = data
        except Exception as e:
            print(f"Warning: Could not load knowledge base: {e}")
    
    def _save_knowledge_base(self):
        """Save knowledge base to disk."""
        if not self.kb_path:
            return
        
        try:
            self.knowledge_base['last_updated'] = datetime.now().isoformat()
            with open(self.kb_path, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge_base, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save knowledge base: {e}")
    
    def _hash_code(self, code: str) -> str:
        """Generate hash for code snippet."""
        return hashlib.sha256(code.encode()).hexdigest()[:16]
    
    def _extract_pattern(self, code: str) -> Optional[str]:
        """Extract pattern from code (e.g., 'font_size_adjustment', 'alignment_fix')."""
        code_lower = code.lower()
        
        if 'font' in code_lower and ('size' in code_lower or 'pt' in code_lower):
            return "font_size_adjustment"
        elif 'alignment' in code_lower or 'align' in code_lower:
            return "alignment_fix"
        elif 'color' in code_lower or 'rgb' in code_lower:
            return "color_adjustment"
        elif 'paragraph' in code_lower or 'bullet' in code_lower:
            return "paragraph_formatting"
        elif 'word_wrap' in code_lower or 'wrap' in code_lower:
            return "text_wrapping"
        elif 'spacing' in code_lower or 'space' in code_lower:
            return "spacing_adjustment"
        
        return None
    
    def record_attempt(
        self,
        code: str,
        quality_before: float,
        quality_after: float,
        issues: List[str],
        success: bool
    ):
        """Record fix attempt and learn from it.
        
        Args:
            code: The generated fix code
            quality_before: Quality score before fix
            quality_after: Quality score after fix
            issues: List of issues that were addressed
            success: Whether the fix improved quality
        """
        code_hash = self._hash_code(code)
        quality_delta = quality_after - quality_before
        pattern = self._extract_pattern(code)
        
        attempt = FixAttempt(
            code_hash=code_hash,
            code_snippet=code[:200],  # Store snippet for reference
            quality_before=quality_before,
            quality_after=quality_after,
            quality_delta=quality_delta,
            issues=issues,
            success=success,
            timestamp=datetime.now().isoformat(),
            pattern=pattern
        )
        
        if success:
            self.knowledge_base['successful_fixes'].append(asdict(attempt))
            # Keep only last 100 successful fixes
            if len(self.knowledge_base['successful_fixes']) > 100:
                self.knowledge_base['successful_fixes'] = \
                    self.knowledge_base['successful_fixes'][-100:]
        else:
            self.knowledge_base['failed_fixes'].append(asdict(attempt))
            # Keep only last 50 failed fixes
            if len(self.knowledge_base['failed_fixes']) > 50:
                self.knowledge_base['failed_fixes'] = \
                    self.knowledge_base['failed_fixes'][-50:]
        
        # Update pattern statistics
        if pattern:
            if pattern not in self.knowledge_base['patterns']:
                self.knowledge_base['patterns'][pattern] = {
                    'success_count': 0,
                    'total_count': 0,
                    'success_rate': 0.0
                }
            
            pattern_data = self.knowledge_base['patterns'][pattern]
            pattern_data['total_count'] += 1
            if success:
                pattern_data['success_count'] += 1
            pattern_data['success_rate'] = \
                pattern_data['success_count'] / pattern_data['total_count']
        
        self._save_knowledge_base()
    
    def get_suggestions(self, issues: List[str], max_patterns: int = 3) -> Dict:
        """Get learned patterns and suggestions for similar issues.
        
        Args:
            issues: List of current issues
            max_patterns: Maximum number of patterns to include (to limit prompt size)
            
        Returns:
            Dictionary with suggestions and successful patterns (limited size)
        """
        suggestions = {
            'successful_patterns': [],
            'failed_patterns': [],
            'pattern_recommendations': {}
        }
        
        # Find similar successful fixes (limit search to recent ones)
        issue_keywords = ' '.join(issues).lower()
        matched_patterns = {}
        
        # Search only most recent fixes (sliding window)
        for fix in self.knowledge_base['successful_fixes'][-20:]:  # Last 20
            fix_issues = ' '.join(fix.get('issues', [])).lower()
            # Simple keyword matching
            if any(keyword in fix_issues for keyword in issue_keywords.split()):
                pattern = fix.get('pattern')
                if pattern:
                    # Track best quality delta per pattern
                    if pattern not in matched_patterns:
                        matched_patterns[pattern] = {
                            'quality_delta': fix['quality_delta'],
                            'code_snippet': fix['code_snippet']
                        }
                    elif fix['quality_delta'] > matched_patterns[pattern]['quality_delta']:
                        # Keep the one with better quality improvement
                        matched_patterns[pattern] = {
                            'quality_delta': fix['quality_delta'],
                            'code_snippet': fix['code_snippet']
                        }
        
        # Sort by quality delta (best improvements first) and limit
        sorted_patterns = sorted(
            matched_patterns.items(),
            key=lambda x: x[1]['quality_delta'],
            reverse=True
        )[:max_patterns]
        
        for pattern, data in sorted_patterns:
            suggestions['successful_patterns'].append({
                'pattern': pattern,
                'quality_delta': data['quality_delta'],
                'code_snippet': data['code_snippet']
            })
        
        # Find failed patterns to avoid (only most recent failures)
        failed_pattern_set = set()
        for fix in self.knowledge_base['failed_fixes'][-10:]:  # Last 10
            pattern = fix.get('pattern')
            if pattern:
                failed_pattern_set.add(pattern)
        
        # Limit failed patterns
        suggestions['failed_patterns'] = [
            {'pattern': p} for p in list(failed_pattern_set)[:max_patterns]
        ]
        
        # Add pattern recommendations (only top performers)
        pattern_stats = []
        for pattern, stats in self.knowledge_base['patterns'].items():
            if stats['total_count'] >= 3:  # Only recommend if tried at least 3 times
                pattern_stats.append((pattern, stats))
        
        # Sort by success rate and total tries, take top ones
        pattern_stats.sort(
            key=lambda x: (x[1]['success_rate'], x[1]['total_count']),
            reverse=True
        )
        
        for pattern, stats in pattern_stats[:5]:  # Top 5 patterns
            suggestions['pattern_recommendations'][pattern] = {
                'success_rate': stats['success_rate'],
                'total_tries': stats['total_count']
            }
        
        return suggestions
    
    def should_avoid_pattern(self, code: str) -> bool:
        """Check if code pattern should be avoided based on past failures.
        
        Args:
            code: Code to check
            
        Returns:
            True if pattern should be avoided
        """
        pattern = self._extract_pattern(code)
        if not pattern:
            return False
        
        pattern_data = self.knowledge_base['patterns'].get(pattern)
        if not pattern_data:
            return False
        
        # Avoid if success rate is very low (< 20%) and tried at least 5 times
        if pattern_data['total_count'] >= 5 and pattern_data['success_rate'] < 0.2:
            return True
        
        return False
