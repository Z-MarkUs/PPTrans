"""AI code generator for PowerPoint fix generation."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .providers.base import TranslationProvider


class AICodeGenerator:
    """Generate Python code fixes based on AI vision review."""
    
    def __init__(self, provider: TranslationProvider, model: str):
        """Initialize code generator.
        
        Args:
            provider: Translation provider (used for code generation)
            model: Model name to use for code generation
        """
        self.provider = provider
        self.model = model
    
    def generate_fix_code(
        self,
        issues: List[str],
        slide_number: int,
        shape_index: int,
        current_state: Dict,
        learning_kb: Optional[Dict] = None
    ) -> str:
        """Generate Python code to fix issues.
        
        Args:
            issues: List of issues detected by vision review
            slide_number: Slide number (1-indexed)
            shape_index: Shape index within slide
            current_state: Current state information (quality, etc.)
            learning_kb: Learning knowledge base suggestions
            
        Returns:
            Generated Python code string
        """
        # Build prompt with context - limit learning KB to prevent prompt bloat
        learning_context = ""
        MAX_LEARNING_TOKENS = 500  # Rough token limit for learning context
        
        if learning_kb:
            token_count = 0
            
            # Add successful patterns (most relevant first, limited)
            if learning_kb.get('successful_patterns'):
                successful_section = "\n\nSuccessful patterns from past fixes:\n"
                for pattern in learning_kb['successful_patterns'][:3]:  # Max 3 patterns
                    snippet = pattern.get('code_snippet', '')[:80]  # Truncate to 80 chars
                    successful_section += f"- {pattern['pattern']}: {snippet}...\n"
                    token_count += len(snippet.split()) + 10  # Rough token estimate
                
                if token_count < MAX_LEARNING_TOKENS:
                    learning_context += successful_section
            
            # Add failed patterns (concise, only if space available)
            if learning_kb.get('failed_patterns') and token_count < MAX_LEARNING_TOKENS:
                failed_section = "\n\nAvoid these patterns (they failed before):\n"
                for pattern in learning_kb['failed_patterns'][:3]:  # Max 3 patterns
                    failed_section += f"- {pattern['pattern']}\n"
                    token_count += 5  # Rough estimate per pattern
                
                if token_count < MAX_LEARNING_TOKENS:
                    learning_context += failed_section
            
            # Add pattern recommendations (summary only, if space available)
            if learning_kb.get('pattern_recommendations') and token_count < MAX_LEARNING_TOKENS:
                rec_section = "\n\nPattern success rates:\n"
                for pattern, stats in list(learning_kb['pattern_recommendations'].items())[:5]:
                    rec_section += f"- {pattern}: {stats['success_rate']:.0%} ({stats['total_tries']} tries)\n"
                    token_count += 8  # Rough estimate per recommendation
                
                if token_count < MAX_LEARNING_TOKENS:
                    learning_context += rec_section
        
        # Use learning context in prompt
        successful_patterns = learning_context
        failed_patterns = ""
        recommendations = ""
        
        prompt = f"""You are fixing PowerPoint translation issues. Generate Python code to fix these problems:

ISSUES TO FIX:
{chr(10).join(f'- {issue}' for issue in issues)}

CONTEXT:
- Slide number: {slide_number}
- Shape index: {shape_index}
- Current quality score: {current_state.get('quality_score', 'unknown')}
{successful_patterns}{failed_patterns}{recommendations}

REQUIREMENTS:
1. You have access to: `slide` (the slide object), `shape_index` (int)
2. Access shape with: `shape = slide.shapes[shape_index]`
3. Available imports: `from pptx.util import Pt`, `from pptx.dml.color import RGBColor`, `from pptx.enum.text import PP_ALIGN`
4. Fix the issues by modifying the shape properties
5. Return ONLY valid Python code, no explanations, no markdown, no code blocks
6. Code should be safe and only modify the specified shape
7. Use proper error handling if needed

EXAMPLE CODE STRUCTURE:
shape = slide.shapes[shape_index]
if hasattr(shape, 'text_frame'):
    # Your fix code here
    pass

Generate the fix code now:"""

        try:
            # Use translation provider's underlying LLM call
            if hasattr(self.provider, 'translate'):
                # We'll use a modified approach - call the provider directly
                response = self._call_provider_for_code(prompt)
            else:
                raise ValueError("Provider does not support code generation")
            
            # Extract code from response
            code = self._extract_code(response)
            return self._sanitize_code(code)
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate fix code: {e}") from e
    
    def _call_provider_for_code(self, prompt: str) -> str:
        """Call provider to generate code."""
        try:
            if hasattr(self.provider, 'translate'):
                # Create a code generation request by modifying the prompt
                # We'll prepend instructions to make it generate code
                code_generation_instruction = (
                    "Generate Python code to fix the following PowerPoint issues. "
                    "Return ONLY the Python code, no explanations, no markdown, no code blocks. "
                    "Just the raw executable Python code.\n\n"
                )
                
                full_prompt = code_generation_instruction + prompt
                
                # Use translate method - it will call the LLM
                # The "target_lang" being "python" is just a hint for the prompt
                response = self.provider.translate(
                    full_prompt,
                    source_lang="en",
                    target_lang="python"
                )
                return response
            elif hasattr(self.provider, 'client'):
                # Direct API call for OpenAI-compatible providers
                from openai import OpenAI
                if isinstance(self.provider.client, OpenAI):
                    response = self.provider.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a Python code generator. Generate ONLY valid Python code, no explanations."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=0.3
                    )
                    return response.choices[0].message.content
            raise ValueError("Provider does not support code generation")
        except Exception as e:
            raise RuntimeError(f"Failed to call provider for code generation: {e}") from e
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response."""
        # Remove markdown code blocks if present
        code = response.strip()
        
        # Remove ```python or ``` markers
        if code.startswith('```'):
            lines = code.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            code = '\n'.join(lines)
        
        # Remove any leading/trailing whitespace
        code = code.strip()
        
        return code
    
    def _sanitize_code(self, code: str) -> str:
        """Sanitize and validate generated code."""
        # Remove dangerous patterns
        dangerous_patterns = [
            r'__import__',
            r'eval\s*\(',
            r'exec\s*\(',
            r'open\s*\(',
            r'file\s*\(',
            r'input\s*\(',
            r'raw_input\s*\(',
            r'subprocess',
            r'os\.system',
            r'shell\s*=\s*True',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                raise SecurityError(f"Dangerous pattern detected: {pattern}")
        
        return code


class SecurityError(Exception):
    """Security violation in generated code."""
    pass




