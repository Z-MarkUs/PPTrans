"""Thread-safe request, upload, slide, and repair budgets for review runs."""

from __future__ import annotations

from enum import Enum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class BudgetLimit(str, Enum):
    REQUESTS = "max_requests"
    SLIDES = "max_slides"
    REPAIR_ROUNDS = "max_repair_rounds_per_slide"
    UPLOAD_PIXELS = "max_upload_megapixels"
    OUTPUT_TOKENS = "max_output_tokens_per_request"


class BudgetExceeded(RuntimeError):  # noqa: N818 - reads naturally at call sites
    """Raised before work begins when a hard review budget would be exceeded."""

    def __init__(self, limit: BudgetLimit, message: str) -> None:
        super().__init__(message)
        self.limit = limit


class BudgetLimits(_FrozenModel):
    max_requests: int = Field(default=40, strict=True, ge=1, le=10_000)
    max_slides: int = Field(default=250, strict=True, ge=1, le=10_000)
    max_repair_rounds_per_slide: int = Field(default=2, strict=True, ge=0, le=10)
    max_upload_megapixels: float = Field(
        default=120.0, strict=True, gt=0.0, le=100_000.0, allow_inf_nan=False
    )
    max_output_tokens_per_request: int = Field(default=1_200, strict=True, ge=64, le=100_000)
    request_timeout_seconds: float = Field(
        default=45.0, strict=True, gt=0.0, le=600.0, allow_inf_nan=False
    )
    max_retries: int = Field(default=1, strict=True, ge=0, le=5)

    @property
    def max_upload_pixels(self) -> int:
        return int(self.max_upload_megapixels * 1_000_000)


class BudgetUsage(_FrozenModel):
    requests: int = 0
    slide_numbers: tuple[int, ...] = ()
    repair_rounds: tuple[tuple[int, int], ...] = ()
    uploaded_pixels: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ReviewBudget:
    """Reserve resources atomically so concurrent workers cannot overspend."""

    def __init__(self, limits: BudgetLimits | None = None) -> None:
        self.limits = limits or BudgetLimits()
        self._requests = 0
        self._slides: set[int] = set()
        self._repair_rounds: dict[int, int] = {}
        self._uploaded_pixels = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._lock = RLock()

    @staticmethod
    def _positive_integer(value: int, name: str, *, allow_zero: bool = False) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        minimum = 0 if allow_zero else 1
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
        return value

    def reserve_slide(self, slide_number: int) -> None:
        slide_number = self._positive_integer(slide_number, "slide_number")
        with self._lock:
            if slide_number in self._slides:
                return
            if len(self._slides) >= self.limits.max_slides:
                raise BudgetExceeded(BudgetLimit.SLIDES, "review slide budget exhausted")
            self._slides.add(slide_number)

    def reserve_request(self, *, image_pixels: int, max_output_tokens: int) -> None:
        image_pixels = self._positive_integer(image_pixels, "image_pixels", allow_zero=True)
        max_output_tokens = self._positive_integer(max_output_tokens, "max_output_tokens")
        with self._lock:
            if self._requests >= self.limits.max_requests:
                raise BudgetExceeded(BudgetLimit.REQUESTS, "review request budget exhausted")
            if max_output_tokens > self.limits.max_output_tokens_per_request:
                raise BudgetExceeded(
                    BudgetLimit.OUTPUT_TOKENS,
                    "request output-token limit exceeds the configured per-request budget",
                )
            if self._uploaded_pixels + image_pixels > self.limits.max_upload_pixels:
                raise BudgetExceeded(
                    BudgetLimit.UPLOAD_PIXELS, "review upload-pixel budget exhausted"
                )
            self._requests += 1
            self._uploaded_pixels += image_pixels

    def reserve_repair_round(self, slide_number: int) -> int:
        slide_number = self._positive_integer(slide_number, "slide_number")
        with self._lock:
            self.reserve_slide(slide_number)
            current = self._repair_rounds.get(slide_number, 0)
            if current >= self.limits.max_repair_rounds_per_slide:
                raise BudgetExceeded(
                    BudgetLimit.REPAIR_ROUNDS,
                    f"repair-round budget exhausted for slide {slide_number}",
                )
            current += 1
            self._repair_rounds[slide_number] = current
            return current

    def record_response_usage(self, *, input_tokens: int | None, output_tokens: int | None) -> None:
        checked_input = (
            None
            if input_tokens is None
            else self._positive_integer(input_tokens, "input_tokens", allow_zero=True)
        )
        checked_output = (
            None
            if output_tokens is None
            else self._positive_integer(output_tokens, "output_tokens", allow_zero=True)
        )
        with self._lock:
            if checked_input is not None:
                self._input_tokens += checked_input
            if checked_output is not None:
                self._output_tokens += checked_output

    def snapshot(self) -> BudgetUsage:
        with self._lock:
            return BudgetUsage(
                requests=self._requests,
                slide_numbers=tuple(sorted(self._slides)),
                repair_rounds=tuple(sorted(self._repair_rounds.items())),
                uploaded_pixels=self._uploaded_pixels,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
            )


__all__ = [
    "BudgetExceeded",
    "BudgetLimit",
    "BudgetLimits",
    "BudgetUsage",
    "ReviewBudget",
]
