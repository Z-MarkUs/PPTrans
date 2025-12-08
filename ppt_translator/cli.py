"""Command line interface for the PPT translator."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .memory import Glossary, TranslationMemory
from .providers import ProviderConfigurationError, create_provider, list_providers
from .translation import TranslationService
from .pipeline import process_ppt_file, regenerate_ppt_from_review
from .utils import clean_path, iter_presentation_files
from .vision import VisionReviewer
from .review import ReviewFileGenerator, ReviewFileLoader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate PowerPoint decks using modern LLM providers.")
    parser.add_argument("path", help="Path to a PPT/PPTX file or a directory containing presentations.")
    parser.add_argument("--source-lang", default="zh", help="Source language code (default: zh).")
    parser.add_argument("--target-lang", default="en", help="Target language code (default: en).")
    parser.add_argument(
        "--provider",
        default="deepseek",
        choices=list_providers(),
        help="Model provider to use for translation.",
    )
    parser.add_argument("--model", help="Optional model override for the chosen provider.")
    parser.add_argument(
        "--max-chunk-size",
        type=int,
        default=1000,
        help="Maximum characters per translation request.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of worker threads used while reading slides.",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep intermediate XML files instead of deleting them.",
    )
    parser.add_argument(
        "--glossary",
        type=str,
        help="Path to glossary file (JSON or YAML) with user-defined translations.",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable translation memory (consistency across slides).",
    )
    parser.add_argument(
        "--vision-review",
        action="store_true",
        help="Enable vision-based review and iterative refinement (requires vision-capable model).",
    )
    parser.add_argument(
        "--vision-quality-threshold",
        type=float,
        default=7.0,
        help="Minimum quality score (0-10) for vision review acceptance (default: 7.0).",
    )
    parser.add_argument(
        "--max-refinement-iterations",
        type=int,
        default=3,
        help="Maximum number of refinement iterations for vision review (default: 3).",
    )
    parser.add_argument(
        "--vision-model",
        type=str,
        help="Vision model to use for review (e.g., gpt-5.1, gpt-4o, gpt-4-vision-preview). Required if --vision-review is enabled.",
    )
    parser.add_argument(
        "--generate-review",
        action="store_true",
        help="Generate interactive review file (JSON/YAML) after translation.",
    )
    parser.add_argument(
        "--review-format",
        choices=["json", "yaml"],
        default="json",
        help="Format for review file (default: json).",
    )
    parser.add_argument(
        "--regenerate-from-review",
        type=str,
        help="Regenerate PPTs from edited review file (provide path to review file).",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    target_path = Path(clean_path(args.path)).expanduser().resolve()

    try:
        provider = create_provider(args.provider, model=args.model)
    except ProviderConfigurationError as exc:
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))

    # Load glossary if provided
    glossary = None
    if args.glossary:
        glossary_path = Path(clean_path(args.glossary)).expanduser().resolve()
        if not glossary_path.exists():
            parser.error(f"Glossary file not found: {glossary_path}")
        glossary = Glossary(glossary_path)
        print(f"Loaded glossary with {glossary.size()} entries from {glossary_path.name}")

    # Create memory file in temp directory (shared across all files in this run)
    memory_file = None
    if not args.no_memory:
        # Use a temp file in the first PPT file's directory
        files = list(iter_presentation_files(target_path))
        if files:
            memory_file = files[0].parent / ".translation_memory.json"
            print(f"Using translation memory: {memory_file.name}")

    translator = TranslationService(
        provider,
        max_chunk_size=args.max_chunk_size,
        memory_file=memory_file,
        glossary=glossary,
    )

    # Initialize vision reviewer if requested
    vision_reviewer = None
    if args.vision_review:
        try:
            # Check if provider supports vision
            if hasattr(provider, 'vision_call'):
                # Prompt user to select vision model if not provided
                vision_model = args.vision_model
                if not vision_model:
                    print("\n🔍 Vision review enabled - Please select a vision model:")
                    print("Available models:")
                    print("  1. gpt-5.1 (Latest, best quality)")
                    print("  2. gpt-4o (Multimodal)")
                    print("  3. gpt-4-vision-preview (Legacy)")
                    print("  4. Custom (enter model name)")
                    
                    while True:
                        choice = input("\nEnter choice (1-4) or model name: ").strip()
                        
                        if choice == "1":
                            vision_model = "gpt-5.1"
                            break
                        elif choice == "2":
                            vision_model = "gpt-4o"
                            break
                        elif choice == "3":
                            vision_model = "gpt-4-vision-preview"
                            break
                        elif choice == "4":
                            vision_model = input("Enter custom model name: ").strip()
                            if vision_model:
                                break
                            print("Please enter a valid model name.")
                        elif choice:
                            # User entered a model name directly
                            vision_model = choice
                            break
                        else:
                            print("Please enter a valid choice.")
                    
                    print(f"Selected model: {vision_model}\n")
                
                vision_reviewer = VisionReviewer(
                    provider,
                    quality_threshold=args.vision_quality_threshold,
                    vision_model=vision_model,
                )
                print(f"Vision review enabled (model: {vision_model}), threshold: {args.vision_quality_threshold}/10")
            else:
                print("Warning: Provider does not support vision calls. Vision review disabled.")
        except Exception as e:
            print(f"Warning: Could not initialize vision reviewer: {e}")

    # Handle regeneration from review file
    if args.regenerate_from_review:
        return _handle_regeneration(
            review_file_path=Path(clean_path(args.regenerate_from_review)).expanduser().resolve(),
            memory_file=memory_file,
        )

    files = list(iter_presentation_files(target_path))
    if not files:
        print("No PowerPoint files were found at the provided location.")
        return 1

    # Initialize review file generator if requested
    review_generator = None
    if args.generate_review:
        review_generator = ReviewFileGenerator(args.source_lang, args.target_lang)

    exit_code = 0
    for file_idx, ppt_file in enumerate(files):
        try:
            result = process_ppt_file(
                ppt_file,
                translator=translator,
                source_lang=args.source_lang,
                target_lang=args.target_lang,
                max_workers=args.max_workers,
                cleanup=not args.keep_intermediate,
                vision_reviewer=vision_reviewer,
                max_refinement_iterations=args.max_refinement_iterations,
                collect_review_data=args.generate_review,
            )
            
            # Handle review data collection
            if args.generate_review:
                output_path, review_slides = result
                if review_slides:
                    # Collect quality scores if available from vision review
                    quality_scores = [s.quality_score for s in review_slides]
                    issues_list = [s.issues for s in review_slides]
                    review_generator.add_file_review(
                        str(ppt_file),
                        review_slides,
                        quality_scores if any(q is not None for q in quality_scores) else None,
                        issues_list if any(issues for issues in issues_list) else None,
                    )
            else:
                output_path = result
        except Exception as exc:  # pragma: no cover - CLI logging
            print(f"Error processing {ppt_file}: {exc}")
            exit_code = 1
    
    # Generate review file if requested
    if args.generate_review and review_generator:
        review_file_path = target_path / f"translation_review.{args.review_format}"
        if target_path.is_file():
            review_file_path = target_path.parent / f"translation_review.{args.review_format}"
        
        try:
            review_generator.save(review_file_path, format=args.review_format)
            print(f"\n✅ Review file generated: {review_file_path.name}")
            print(f"   Edit this file and use --regenerate-from-review to apply changes")
        except Exception as e:
            print(f"\n⚠️  Warning: Could not generate review file: {e}")
    
    # Clean up memory file if requested
    if memory_file and memory_file.exists() and not args.keep_intermediate:
        try:
            memory_file.unlink()
            print(f"Translation memory cleaned up.")
        except Exception:
            pass

    return exit_code


def _handle_regeneration(review_file_path: Path, memory_file: Optional[Path] = None) -> int:
    """Handle regeneration from edited review file."""
    try:
        print(f"Loading review file: {review_file_path.name}")
        review_data = ReviewFileLoader.load(review_file_path)
        
        # Validate review file
        is_valid, errors = ReviewFileLoader.validate(review_data)
        if not is_valid:
            print("❌ Review file validation failed:")
            for error in errors:
                print(f"   - {error}")
            return 1
        
        print(f"✅ Review file validated: {review_data.total_files} file(s), {review_data.total_slides} slide(s)")
        
        # Load translation memory if available
        translation_memory = None
        if memory_file and memory_file.exists():
            translation_memory = TranslationMemory(memory_file)
            print(f"Using translation memory: {memory_file.name}")
        
        # Regenerate each file
        for file_idx, file_review in enumerate(review_data.files):
            original_ppt_path = Path(file_review.file_path)
            if not original_ppt_path.exists():
                print(f"⚠️  Warning: Original file not found: {original_ppt_path}")
                continue
            
            # Determine output path
            output_path = original_ppt_path.parent / f"{original_ppt_path.stem}_final{original_ppt_path.suffix}"
            
            print(f"\n📝 Regenerating: {original_ppt_path.name} → {output_path.name}")
            regenerate_ppt_from_review(
                original_ppt_path=original_ppt_path,
                review_data=review_data,
                file_index=file_idx,
                output_path=output_path,
                update_memory=translation_memory,
            )
        
        print(f"\n✅ Regeneration complete! {len(review_data.files)} file(s) regenerated.")
        return 0
    
    except Exception as e:
        print(f"❌ Error during regeneration: {e}")
        return 1


def main() -> None:
    sys.exit(run_cli())
