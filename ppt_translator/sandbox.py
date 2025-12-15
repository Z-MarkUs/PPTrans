"""Sandbox executor for safely running AI-generated code."""
from __future__ import annotations

import re
from typing import Tuple, Optional, Dict, Any
from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


class SandboxExecutor:
    """Safely execute AI-generated code in restricted environment."""
    
    # Allowed imports and functions
    ALLOWED_BUILTINS = {
        'len', 'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple',
        'range', 'enumerate', 'zip', 'min', 'max', 'abs', 'round',
        'hasattr', 'getattr', 'setattr', 'isinstance', 'type'
    }
    
    RESTRICTED_PATTERNS = [
        r'__import__',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'open\s*\(',
        r'file\s*\(',
        r'input\s*\(',
        r'subprocess',
        r'os\.',
        r'sys\.',
        r'import\s+os',
        r'import\s+sys',
        r'import\s+subprocess',
        r'shell\s*=\s*True',
        r'\.__',
    ]
    
    def __init__(self):
        """Initialize sandbox executor."""
        pass
    
    def execute_fix(
        self,
        code: str,
        presentation: Presentation,
        slide_number: int,
        shape_index: int
    ) -> Tuple[bool, Optional[Exception], Optional[str]]:
        """Execute fix code in sandbox.
        
        Args:
            code: Python code to execute
            presentation: PowerPoint presentation object
            slide_number: Slide number (1-indexed)
            shape_index: Shape index within slide
            
        Returns:
            Tuple of (success, error, result_message)
        """
        # Validate code first
        validation_error = self._validate_code(code)
        if validation_error:
            return False, SecurityError(validation_error), None
        
        # Create safe execution environment
        try:
            slide = presentation.slides[slide_number - 1]  # Convert to 0-indexed
            
            # Safe globals - only allow specific functions
            safe_globals: Dict[str, Any] = {
                '__builtins__': {name: __builtins__[name] for name in self.ALLOWED_BUILTINS 
                                if name in __builtins__},
                'slide': slide,
                'shape_index': shape_index,
                'Pt': Pt,
                'RGBColor': RGBColor,
                'PP_ALIGN': PP_ALIGN,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'isinstance': isinstance,
                'type': type,
            }
            
            # Safe locals
            safe_locals = {}
            
            # Execute code
            exec(code, safe_globals, safe_locals)
            
            return True, None, "Fix applied successfully"
            
        except SecurityError as e:
            return False, e, None
        except Exception as e:
            return False, e, str(e)
    
    def _validate_code(self, code: str) -> Optional[str]:
        """Validate code for security issues.
        
        Args:
            code: Code to validate
            
        Returns:
            Error message if validation fails, None otherwise
        """
        # Check for restricted patterns
        for pattern in self.RESTRICTED_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return f"Restricted pattern detected: {pattern}"
        
        # Check for imports (only allow specific ones)
        import_lines = [line for line in code.split('\n') 
                       if line.strip().startswith('import') or line.strip().startswith('from')]
        
        allowed_imports = ['pptx', 'Pt', 'RGBColor', 'PP_ALIGN']
        for import_line in import_lines:
            # Allow imports from pptx modules
            if not any(allowed in import_line for allowed in allowed_imports):
                if 'import' in import_line or 'from' in import_line:
                    return f"Unauthorized import detected: {import_line.strip()}"
        
        # Check code length (prevent extremely long code)
        if len(code) > 5000:
            return "Code too long (max 5000 characters)"
        
        # Check for nested exec/eval attempts
        if 'exec(' in code.replace(' ', '') or 'eval(' in code.replace(' ', ''):
            return "Nested exec/eval detected"
        
        return None


class SecurityError(Exception):
    """Security violation in code execution."""
    pass
