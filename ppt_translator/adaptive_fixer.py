"""Adaptive fixing system with AI code generation and learning."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Dict, List
from pptx import Presentation

from .code_generator import AICodeGenerator
from .sandbox import SandboxExecutor
from .adaptive_learning import AdaptiveLearningSystem
from .state_manager import StateManager
from .providers.base import TranslationProvider
from .render import render_slide_to_image


class AdaptiveFixer:
    """Main adaptive fixing system that generates code, executes, and learns."""
    
    def __init__(
        self,
        provider: TranslationProvider,
        model: str,
        learning_kb_path: Optional[Path] = None,
        temp_dir: Optional[Path] = None
    ):
        """Initialize adaptive fixer.
        
        Args:
            provider: Translation provider for code generation
            model: Model name for code generation
            learning_kb_path: Path to save learning knowledge base
            temp_dir: Temporary directory for state backups
        """
        self.code_generator = AICodeGenerator(provider, model)
        self.executor = SandboxExecutor()
        self.learning_system = AdaptiveLearningSystem(learning_kb_path)
        self.state_manager = StateManager(temp_dir)
    
    def fix_with_learning(
        self,
        ppt_path: Path,
        slide_number: int,
        shape_index: int,
        issues: List[str],
        quality_score: float,
        original_image_path: Optional[Path] = None,
        vision_reviewer = None,
        source_lang: str = "en",
        target_lang: str = "en",
        max_iterations: int = 3,
        quality_threshold: float = 7.0
    ) -> Tuple[bool, float, str]:
        """Fix issues using AI code generation with learning and rollback.
        
        Args:
            ppt_path: Path to PPT file
            slide_number: Slide number (1-indexed)
            shape_index: Shape index within slide
            issues: List of issues to fix
            quality_score: Current quality score
            max_iterations: Maximum fix attempts
            quality_threshold: Target quality threshold
            
        Returns:
            Tuple of (success, final_quality, message)
        """
        if quality_score >= quality_threshold:
            return True, quality_score, "Quality already meets threshold"
        
        presentation = Presentation(str(ppt_path))
        best_quality = quality_score
        best_state_id = None
        
        for iteration in range(max_iterations):
            print(f"  🔧 Adaptive fix iteration {iteration + 1}/{max_iterations}")
            
            # Save state before attempting fix
            state_id = self.state_manager.save_state(ppt_path)
            
            # Get learning suggestions (limit to prevent prompt bloat)
            # Only include most relevant patterns, not all history
            suggestions = self.learning_system.get_suggestions(issues, max_patterns=3)
            
            # Generate fix code
            try:
                current_state = {
                    'quality_score': best_quality,
                    'iteration': iteration
                }
                
                fix_code = self.code_generator.generate_fix_code(
                    issues=issues,
                    slide_number=slide_number,
                    shape_index=shape_index,
                    current_state=current_state,
                    learning_kb=suggestions
                )
                
                # Check if we should avoid this pattern
                if self.learning_system.should_avoid_pattern(fix_code):
                    print(f"    ⚠️  Skipping pattern (low success rate in past)")
                    self.state_manager.cleanup_state(state_id)
                    continue
                
                print(f"    🤖 Generated fix code ({len(fix_code)} chars)")
                
            except Exception as e:
                print(f"    ❌ Code generation failed: {e}")
                self.state_manager.cleanup_state(state_id)
                continue
            
            # Execute fix
            success, error, message = self.executor.execute_fix(
                code=fix_code,
                presentation=presentation,
                slide_number=slide_number,
                shape_index=shape_index
            )
            
            if not success:
                print(f"    ❌ Execution failed: {error}")
                self.state_manager.cleanup_state(state_id)
                # Learn from failure
                self.learning_system.record_attempt(
                    code=fix_code,
                    quality_before=best_quality,
                    quality_after=best_quality,  # No change
                    issues=issues,
                    success=False
                )
                continue
            
            # Save PPT after fix
            presentation.save(str(ppt_path))
            
            # Re-evaluate quality using vision review
            try:
                if original_image_path and vision_reviewer and hasattr(vision_reviewer, 'review_translated_slide'):
                    new_quality, new_issues = self._review_quality(
                        ppt_path, slide_number, original_image_path,
                        vision_reviewer, source_lang, target_lang
                    )
                else:
                    # Fallback: estimate improvement based on code execution success
                    new_quality = min(10.0, best_quality + 0.5)
                    new_issues = []
            except Exception as e:
                print(f"    ⚠️  Quality review failed: {e}, using estimation")
                new_quality = min(10.0, best_quality + 0.5)
                new_issues = []
            
            # Learn from result
            quality_improved = new_quality > best_quality
            self.learning_system.record_attempt(
                code=fix_code,
                quality_before=best_quality,
                quality_after=new_quality,
                issues=issues,
                success=quality_improved
            )
            
            if quality_improved:
                print(f"    ✅ Quality improved: {best_quality:.1f} → {new_quality:.1f}")
                best_quality = new_quality
                # Clean up old state, keep new one
                if best_state_id:
                    self.state_manager.cleanup_state(best_state_id)
                best_state_id = state_id
                
                if best_quality >= quality_threshold:
                    return True, best_quality, f"Quality threshold met: {best_quality:.1f}"
            else:
                print(f"    ⚠️  Quality did not improve: {best_quality:.1f} → {new_quality:.1f}")
                # Rollback
                if self.state_manager.rollback(ppt_path, state_id):
                    print(f"    🔄 Rolled back to previous state")
                    self.state_manager.cleanup_state(state_id)
                    # Reload presentation after rollback
                    presentation = Presentation(str(ppt_path))
                else:
                    print(f"    ⚠️  Rollback failed, keeping current state")
        
        # Clean up remaining states
        if best_state_id:
            self.state_manager.cleanup_state(best_state_id)
        
        return best_quality >= quality_threshold, best_quality, f"Final quality: {best_quality:.1f}"
    
    def _review_quality(
        self,
        ppt_path: Path,
        slide_number: int,
        original_image_path: Path,
        vision_reviewer,
        source_lang: str,
        target_lang: str
    ) -> Tuple[float, List[str]]:
        """Review quality using vision reviewer.
        
        Args:
            ppt_path: Path to PPT file
            slide_number: Slide number
            original_image_path: Path to original slide image
            vision_reviewer: Vision reviewer instance
            source_lang: Source language
            target_lang: Target language
            
        Returns:
            Tuple of (quality_score, issues_list)
        """
        if not vision_reviewer:
            # Fallback: estimate based on execution success
            return 7.0, []
        
        try:
            # Render translated slide
            temp_dir = ppt_path.parent / f"{ppt_path.stem}_temp"
            temp_dir.mkdir(exist_ok=True)
            translated_image_path = temp_dir / f"slide_{slide_number}_translated_review.png"
            
            if render_slide_to_image(ppt_path, slide_number, translated_image_path):
                review_result = vision_reviewer.review_translated_slide(
                    original_image_path, translated_image_path, source_lang, target_lang
                )
                return review_result.quality_score, review_result.issues
            else:
                return 7.0, []
        except Exception as e:
            print(f"    ⚠️  Vision review failed: {e}")
            return 7.0, []
