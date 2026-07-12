"""Typer CLI entry point — generate, list-refs, and history commands."""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from providers.nano_banana_pro import NanoBananaProProvider
from providers.prompt_refiner import PromptRefiner
from utils.manifest import append_entry, normalize_path, read_entries

load_dotenv()

app = typer.Typer()
console = Console()


@app.callback()
def callback() -> None:
    """myt-image-gen — AI image generation CLI for MYT campaigns."""


SETTINGS_PATH = Path(__file__).parent / "config" / "settings.yaml"
BRAND_GUIDE_PATH = Path(__file__).parent / "reference-images" / "brand-guide.md"
PROMPTING_GUIDE_PATH = Path(__file__).parent / "docs" / "prompting-guide.md"
REF_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_COUNT = 10
MAX_REFERENCE_IMAGES = 14
STATUS_COLORS = {"success": "green", "partial": "yellow", "failed": "red"}


def _load_settings() -> dict:
    """Load config/settings.yaml into a dict."""
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_brand_guide() -> str:
    """Read brand-guide.md content, or an empty string if it's missing or blank."""
    if not BRAND_GUIDE_PATH.exists():
        return ""
    return BRAND_GUIDE_PATH.read_text(encoding="utf-8").strip()


def _load_prompting_guide() -> str:
    """Read docs/prompting-guide.md content, or an empty string if it's missing or blank."""
    if not PROMPTING_GUIDE_PATH.exists():
        return ""
    return PROMPTING_GUIDE_PATH.read_text(encoding="utf-8").strip()


def _assemble_prompt(user_prompt: str) -> str:
    """Prepend brand guide content to the user's prompt so brand consistency is automatic."""
    brand_guide = _load_brand_guide()
    if not brand_guide:
        return user_prompt
    return f"{brand_guide}\n\n---\n\n{user_prompt}"


def _collect_reference_images(campaign_dir: Path) -> list[Path]:
    """Glob a campaign folder for supported image files, alphabetical order.

    Truncates to the first MAX_REFERENCE_IMAGES and warns, since the model
    accepts at most 14 reference images per call.
    """
    images = sorted(p for p in campaign_dir.iterdir() if p.suffix.lower() in REF_EXTENSIONS)
    if len(images) > MAX_REFERENCE_IMAGES:
        console.print(
            f"[yellow]Warning: campaign folder has {len(images)} images, using only the "
            f"first {MAX_REFERENCE_IMAGES} (alphabetical).[/yellow]"
        )
        images = images[:MAX_REFERENCE_IMAGES]
    return images


@dataclass
class RefinementResult:
    """Outcome of the interactive refinement step, ready to feed into _assemble_prompt / the manifest."""

    final_prompt: str
    refined_prompt: str | None = None
    qa: list[dict] = field(default_factory=list)
    aborted: bool = False


def _refine_prompt(raw_prompt: str, campaign: str, reference_images: list[Path], settings: dict) -> RefinementResult:
    """Ask clarifying questions (with recommended defaults) and synthesize a polished prompt.

    Never raises — any refiner API failure prints a warning and falls back to raw_prompt
    so refinement can never block or crash a generate call.
    """
    console.print(f"\n[bold cyan]Refining prompt for '{campaign}'...[/bold cyan]")
    refiner = PromptRefiner(model_name=settings["refiner_model_string"])
    brand_guide = _load_brand_guide()
    max_questions = settings["max_refinement_questions"]

    try:
        with console.status("[bold cyan]Checking prompt for ambiguities...[/bold cyan]"):
            questions = refiner.generate_questions(
                user_prompt=raw_prompt,
                campaign=campaign,
                reference_filenames=[p.name for p in reference_images],
                brand_guide=brand_guide,
                max_questions=max_questions,
            )
    except Exception as e:
        console.print(f"[yellow]Warning: prompt refinement unavailable ({e}). Continuing with your original prompt.[/yellow]")
        return RefinementResult(final_prompt=raw_prompt)

    if not questions:
        console.print("[green]Prompt looks sufficiently detailed — no clarifying questions needed.[/green]")
        return RefinementResult(final_prompt=raw_prompt)

    console.print(f"\n[bold]{len(questions)} clarifying question(s) — press Enter to accept the recommended answer.[/bold]")
    qa: list[dict] = []
    for i, q in enumerate(questions, start=1):
        answer = Prompt.ask(f"[cyan]{i}. {q.question}[/cyan]", default=q.recommended_answer)
        qa.append({"question": q.question, "recommended_answer": q.recommended_answer, "answer": answer})

    try:
        with console.status("[bold cyan]Synthesizing refined prompt...[/bold cyan]"):
            polished = refiner.synthesize_prompt(
                user_prompt=raw_prompt, campaign=campaign, qa=qa, prompting_guide=_load_prompting_guide()
            )
    except Exception as e:
        console.print(f"[yellow]Warning: prompt synthesis failed ({e}). Continuing with your original prompt.[/yellow]")
        return RefinementResult(final_prompt=raw_prompt, qa=qa)

    console.print("\n[bold]Refined prompt:[/bold]")
    console.print(polished)
    if not Confirm.ask("\nUse this refined prompt for generation?", default=True):
        console.print("[yellow]Generation cancelled — no image was generated.[/yellow]")
        return RefinementResult(final_prompt=raw_prompt, refined_prompt=polished, qa=qa, aborted=True)

    return RefinementResult(final_prompt=polished, refined_prompt=polished, qa=qa)


@app.command()
def generate(
    prompt: str = typer.Option(..., "--prompt", help="Prompt text for image generation."),
    campaign: str = typer.Option(..., "--campaign", help="Campaign name, maps to reference-images/<campaign>/."),
    refs: str | None = typer.Option(None, "--refs", help="Comma-separated reference image filenames. Defaults to all images in the campaign folder."),
    count: int | None = typer.Option(None, "--count", help="Number of images to generate."),
    aspect_ratio: str | None = typer.Option(None, "--aspect-ratio", help="Output aspect ratio."),
    resolution: str | None = typer.Option(None, "--resolution", help="Output resolution: 1K, 2K, or 4K."),
    refine: bool = typer.Option(True, "--refine/--no-refine", help="Run AI prompt refinement (clarifying questions + synthesis) before generating. On by default."),
) -> None:
    """Generate images for a campaign and log the attempt to the manifest."""
    if not os.getenv("GEMINI_API_KEY"):
        console.print("[red]Error: GEMINI_API_KEY is not set. Add it to .env before generating images.[/red]")
        raise typer.Exit(code=1)

    settings = _load_settings()
    count = count or settings["default_count"]
    aspect_ratio = aspect_ratio or settings["default_aspect_ratio"]
    resolution = resolution or settings["default_resolution"]

    if count > MAX_COUNT:
        console.print(f"[red]Error: --count {count} exceeds the maximum of {MAX_COUNT}.[/red]")
        raise typer.Exit(code=1)

    reference_dir = Path(settings["reference_dir"]) / campaign
    if not reference_dir.exists():
        console.print(
            f"[red]Campaign '{campaign}' not found at {normalize_path(reference_dir)}/. "
            f"Create the folder first (it can be empty) or check for a typo.[/red]"
        )
        raise typer.Exit(code=1)

    if refs:
        reference_images = [reference_dir / name.strip() for name in refs.split(",")]
    else:
        reference_images = _collect_reference_images(reference_dir)

    if refine:
        refinement = _refine_prompt(prompt, campaign, reference_images, settings)
        if refinement.aborted:
            raise typer.Exit(code=0)
    else:
        refinement = RefinementResult(final_prompt=prompt)

    output_dir = Path(settings["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    full_prompt = _assemble_prompt(refinement.final_prompt)

    try:
        provider = NanoBananaProProvider(model_name=settings["model_string"])
        result = provider.generate(
            prompt=full_prompt,
            campaign=campaign,
            reference_images=reference_images,
            count=count,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            output_dir=output_dir,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaign": campaign,
        "prompt": full_prompt,
        "user_prompt": prompt,
        "refined_prompt": refinement.refined_prompt,
        "refinement_qa": refinement.qa,
        "model": settings["model_string"],
        "reference_images": [normalize_path(p) for p in reference_images],
        "params": {"aspect_ratio": aspect_ratio, "resolution": resolution, "count": count},
        "outputs": [normalize_path(p) for p in result.output_paths],
        "status": result.status,
        "error": "; ".join(result.errors) if result.errors else None,
    }
    append_entry(Path(settings["manifest_path"]), entry)

    console.print(f"Generation summary - {campaign}")
    table = Table()
    table.add_column("#")
    table.add_column("Status")
    table.add_column("File / Error")
    for i, outcome in enumerate(result.outcomes, start=1):
        if outcome.success:
            table.add_row(str(i), "[green]OK[/green]", str(outcome.path))
        else:
            table.add_row(str(i), "[red]FAILED[/red]", outcome.error or "")
    console.print(table)

    color = STATUS_COLORS.get(result.status, "white")
    console.print(f"Status: [{color}]{result.status}[/{color}]")


@app.command(name="list-refs")
def list_refs(
    campaign: str | None = typer.Option(None, "--campaign", help="List files within a specific campaign."),
) -> None:
    """List available campaign folders, or files within one campaign."""
    settings = _load_settings()
    reference_dir = Path(settings["reference_dir"])

    if campaign:
        campaign_dir = reference_dir / campaign
        if not campaign_dir.exists():
            console.print(f"[red]Campaign '{campaign}' not found at {normalize_path(campaign_dir)}/.[/red]")
            raise typer.Exit(code=1)
        images = sorted(p for p in campaign_dir.iterdir() if p.suffix.lower() in REF_EXTENSIONS)
        console.print(f"Reference images - {campaign}")
        table = Table()
        table.add_column("File")
        for p in images:
            table.add_row(p.name)
        console.print(table)
        if len(images) > MAX_REFERENCE_IMAGES:
            console.print(
                f"[yellow]Note: {len(images)} images found; a generate call would use only "
                f"the first {MAX_REFERENCE_IMAGES} (alphabetical).[/yellow]"
            )
        return

    campaigns = sorted((p for p in reference_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    console.print("Campaigns")
    table = Table()
    table.add_column("Campaign")
    table.add_column("Images", justify="right")
    for c in campaigns:
        image_count = len([p for p in c.iterdir() if p.suffix.lower() in REF_EXTENSIONS])
        table.add_row(c.name, str(image_count))
    console.print(table)


@app.command()
def history(
    campaign: str | None = typer.Option(None, "--campaign", help="Filter by campaign."),
    limit: int = typer.Option(10, "--limit", help="Max number of entries to show."),
) -> None:
    """Show past generations from the manifest, most recent first."""
    settings = _load_settings()
    entries = read_entries(Path(settings["manifest_path"]))
    if campaign:
        entries = [e for e in entries if e["campaign"] == campaign]
    entries = list(reversed(entries))[:limit]

    console.print("Generation history")
    table = Table()
    table.add_column("Timestamp", overflow="fold")
    table.add_column("Campaign")
    table.add_column("Prompt")
    table.add_column("Outputs", overflow="fold")
    table.add_column("Status")
    for e in entries:
        preview_source = e.get("user_prompt", e["prompt"])
        preview = preview_source if len(preview_source) <= 60 else preview_source[:57] + "..."
        outputs = ", ".join(Path(p).name for p in e["outputs"])
        status = e["status"]
        color = STATUS_COLORS.get(status, "white")
        table.add_row(e["timestamp"], e["campaign"], preview, outputs, f"[{color}]{status}[/{color}]")
    console.print(table)


if __name__ == "__main__":
    app()
