"""Shared abstract interface every image-generation provider must implement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageOutcome:
    """Outcome of generating a single image within a batch."""

    success: bool
    path: Path | None = None
    error: str | None = None


@dataclass
class GenerationResult:
    """Outcome of a generate() call, shaped to drop directly into a manifest entry."""

    outcomes: list[ImageOutcome] = field(default_factory=list)

    @property
    def status(self) -> str:
        """"success" if every image succeeded, "partial" if some did, "failed" if none did."""
        successes = [o for o in self.outcomes if o.success]
        if not successes:
            return "failed"
        if len(successes) == len(self.outcomes):
            return "success"
        return "partial"

    @property
    def output_paths(self) -> list[Path]:
        """Paths of the images that were actually saved."""
        return [o.path for o in self.outcomes if o.success and o.path is not None]

    @property
    def errors(self) -> list[str]:
        """Error messages from images that failed."""
        return [o.error for o in self.outcomes if not o.success and o.error]


class BaseImageProvider(ABC):
    """Abstract base class defining the contract all image providers must follow."""

    # Universal across providers per config/settings.yaml's allowed values.
    SUPPORTED_RESOLUTIONS: tuple[str, ...] = ("1K", "2K", "4K")
    # Each subclass overrides this with the ratios its model actually supports.
    SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ()

    def __init__(self, model_name: str) -> None:
        """Store the model identifier, supplied by the caller from config — never hardcoded."""
        self.model_name = model_name

    def validate_params(self, aspect_ratio: str, resolution: str) -> None:
        """Raise ValueError if aspect_ratio or resolution aren't supported, before any API call."""
        if resolution not in self.SUPPORTED_RESOLUTIONS:
            raise ValueError(
                f"Unsupported resolution '{resolution}'. Allowed: {', '.join(self.SUPPORTED_RESOLUTIONS)}"
            )
        if aspect_ratio not in self.SUPPORTED_ASPECT_RATIOS:
            raise ValueError(
                f"Unsupported aspect ratio '{aspect_ratio}'. Allowed: {', '.join(self.SUPPORTED_ASPECT_RATIOS)}"
            )

    def build_output_path(self, campaign: str, timestamp: str, index: int, output_dir: Path) -> Path:
        """Build the {campaign}_{timestamp}_{n}.png path, incrementing a suffix on collision."""
        base_name = f"{campaign}_{timestamp}_{index}"
        candidate = output_dir / f"{base_name}.png"
        suffix = 1
        while candidate.exists():
            candidate = output_dir / f"{base_name}_{suffix}.png"
            suffix += 1
        return candidate

    @abstractmethod
    def generate(
        self,
        prompt: str,
        campaign: str,
        reference_images: list[Path],
        count: int,
        aspect_ratio: str,
        resolution: str,
        output_dir: Path,
    ) -> GenerationResult:
        """Generate `count` images and save them to output_dir.

        Implementations must never raise on API/network errors — catch them
        and return GenerationResult(success=False, error=...) so the caller
        can always log the attempt to the manifest.
        """
        raise NotImplementedError
