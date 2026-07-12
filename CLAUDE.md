1# myt-image-gen — Project Context

## What This Is
A solo-use, local CLI tool for generating AI images for MyYogaTeacher (MYT)
articles and ad campaigns. Runs entirely on Rahul's machine via terminal —
no hosting, no server, no multi-user access, no web UI (may be added later,
not now).

Core flow: prompt + reference images (per campaign) → image model → images
saved locally → every generation logged to a manifest.

## Tech Stack
- Python 3.11+
- Typer — CLI command structure
- Rich — terminal output (progress, tables, colored status)
- google-genai — official Google SDK, used to call Nano Banana Pro
- PyYAML — reads config/settings.yaml
- python-dotenv — loads GEMINI_API_KEY from .env
- Pillow — image handling/saving

## Image Model
Nano Banana Pro = Gemini 3 Pro Image (`gemini-3-pro-image`). Accessed only
through the provider interface below — never call google-genai directly
from main.py or anywhere outside providers/.

Model supports: up to 14 reference images per call, native 1K/2K/4K output,
multiple aspect ratios, accurate text rendering, multi-turn conversational
editing. The "-preview" suffix may appear in the raw model string as Google
moves this to general availability — keep the exact model string isolated
in config/settings.yaml, never hardcoded in provider code, so a rename is
a one-line config fix.

## Prompt Refinement
Before a `--prompt` reaches the image model, `providers/prompt_refiner.py`
runs an interactive refinement step (on by default; skip with `--no-refine`)
using a separate, cheaper Gemini text model (`refiner_model_string` in
config, isolated from code the same way `model_string` is) — never the
expensive image model.

Two lightweight text-only calls, both accessed only through
`PromptRefiner` (never google-genai directly from main.py, same guardrail
as the image model):
1. **Clarifying questions** — reads the raw prompt, campaign name,
   reference image filenames, and brand-guide.md content (text only, no
   actual reference images sent). Returns up to `max_refinement_questions`
   questions, each with an on-brand recommended answer (Enter accepts it).
   Returns zero questions if the prompt is already unambiguous, in which
   case refinement stops here — no second call, no wasted spend.
2. **Synthesis** — once questions are answered, merges the original
   prompt + Q&A into one polished paragraph. Shown to the user for
   confirmation (default yes) before it's brand-guide-assembled and sent
   to the image model; declining cancels the call cleanly with no image
   API call and no manifest entry.

Fail-open by design: any refiner API error is caught in main.py (the
provider methods themselves raise — main.py's `_refine_prompt` decides
the fallback), prints a warning, and falls back to the user's original
raw prompt. Refinement must never block or crash a `generate` call.

## File Structure
myt-image-gen/
├── main.py                     # Typer app — CLI entry point, defines subcommands
├── config/
│   └── settings.yaml           # default model, resolution, aspect ratio, count, paths
├── providers/
│   ├── base.py                 # BaseImageProvider abstract class — the shared interface
│   ├── nano_banana_pro.py      # Nano Banana Pro implementation of BaseImageProvider
│   └── prompt_refiner.py       # text-only prompt refinement (clarifying Q&A + synthesis) — not a BaseImageProvider
├── reference-images/
│   ├── brand-guide.md          # tone, do's/don'ts, general style notes
│   └── <campaign-name>/        # one subfolder per campaign, e.g. postpartum-yoga/
├── output/
│   ├── manifest.json           # log of every generation call (see schema below)
│   └── *.png                   # flat — all generated images live directly here
├── docs/
│   ├── decisions.md            # every key decision + reasoning, dated
│   ├── progress.md             # what's built, current status, what's next
│   └── prompting-guide.md      # keyword/phrasing checklist for writing on-brand, unambiguous --prompt text
├── utils/
│   ├── manifest.py             # read/write helpers for manifest.json
│   └── retry.py                # shared exponential-backoff retry wrapper for google-genai calls
├── .env                        # GEMINI_API_KEY — never committed
└── .env.example                # template, safe to commit

## CLI Commands
- `python main.py generate --prompt "..." --campaign postpartum-yoga [--refs file1.png,file2.png] [--count 3] [--aspect-ratio 1:1] [--resolution 2K] [--refine/--no-refine]`
  - `--campaign` maps to `reference-images/<campaign>/` — if `--refs` is omitted, all images in that campaign folder are used automatically
  - `--count` defaults to 3 (config default), `--aspect-ratio` and `--resolution` fall back to config/settings.yaml if omitted
  - Campaign folder with zero reference images is valid — falls back to text-only generation
  - `--refine/--no-refine` (default: `--refine`) — before generation, runs a text-only prompt-refinement step using a separate, cheaper Gemini text model (`refiner_model_string`). It reads the raw prompt, campaign name, reference image filenames, and brand-guide.md, and asks up to `max_refinement_questions` clarifying questions (each with a recommended default — press Enter to accept). If the prompt is already unambiguous, zero questions are asked and refinement is skipped. Otherwise a second lightweight call synthesizes the prompt + your answers into one polished paragraph, shown to you for confirmation (default yes) before it's brand-guide-assembled and sent to the image model — decline to cancel the call with no image API call made and no manifest entry. Any refinement API failure prints a warning and falls back to your original prompt; it never blocks generation. Use `--no-refine` to skip entirely.
- `python main.py list-refs [--campaign postpartum-yoga]` — lists available campaign folders, or files within one campaign, so Rahul can check what's available before generating
- `python main.py history [--campaign postpartum-yoga] [--limit 10]` — reads manifest.json, shows past generations as a Rich table (timestamp, campaign, prompt preview, output files, status)

## Config (config/settings.yaml)
```yaml
default_model: nano_banana_pro
model_string: gemini-3-pro-image   # the exact model string passed to google-genai; isolated here per the Image Model section above
refiner_model_string: gemini-2.5-flash   # cheaper/faster text-only model used for prompt refinement (see Prompt Refinement below); isolated here for the same reason
max_refinement_questions: 4        # cap on clarifying questions per generate call — the refiner may return fewer, or zero if the prompt is already unambiguous
default_count: 3
default_aspect_ratio: "1:1"
default_resolution: "2K"     # allowed: 1K, 2K, 4K
output_dir: output
reference_dir: reference-images
manifest_path: output/manifest.json
```

## Manifest Schema (output/manifest.json)
One JSON array, one entry per `generate` call (not per image):
```json
{
  "id": "uuid",
  "timestamp": "2026-07-07T14:32:00Z",
  "campaign": "postpartum-yoga",
  "prompt": "full prompt text as submitted, including the auto-injected brand-guide.md content",
  "user_prompt": "just the raw --prompt text the user typed, used for history's preview column",
  "refined_prompt": "the polished paragraph produced by prompt refinement, or null if --no-refine was used, the prompt was already unambiguous (no questions asked), or a refinement API call failed and fell back to user_prompt",
  "refinement_qa": [{"question": "...", "recommended_answer": "...", "answer": "..."}],
  "model": "gemini-3-pro-image",
  "reference_images": ["reference-images/postpartum-yoga/hero-shot.png"],
  "params": {"aspect_ratio": "1:1", "resolution": "2K", "count": 3},
  "outputs": [
    "output/postpartum-yoga_20260707-1432_1.png",
    "output/postpartum-yoga_20260707-1432_2.png",
    "output/postpartum-yoga_20260707-1432_3.png"
  ],
  "status": "success",
  "error": null
}
```
`refinement_qa` is `[]` when refinement was skipped (`--no-refine`), when the refiner
found the prompt unambiguous, or when a refinement API call failed and the tool fell
back to the raw prompt.

`status` is one of `"success"` (all images in the batch succeeded), `"partial"` (some
succeeded — `outputs` lists only the successes, `error` describes the failures), or
`"failed"` (none succeeded).

## Naming Convention
`{campaign}_{YYYYMMDD-HHMM}_{n}.png` — e.g. `postpartum-yoga_20260707-1432_1.png`

## Brand Convention
If any generated image includes visible text mentioning the brand, always
use the full name "MyYogaTeacher" — never "MYT". This matches the standing
convention used across all MYT customer-facing copy.

## Brand Guide Maintenance
`reference-images/brand-guide.md` is a living document, not a one-time
artifact. Whenever a session surfaces feedback on a generation's prompt or
output that reveals a brand/visual preference not yet captured there
(a rejected pose, a setting that felt off-brand, a representation note,
etc.), update brand-guide.md in that same session — don't wait until end
of session — and log the change with reasoning in docs/decisions.md.

## Guardrails — Always
- Read CLAUDE.md, docs/decisions.md, and docs/progress.md at the start of every session
- Call image models only through providers/base.py's interface — never call google-genai directly from main.py or utils/
- Log every generation attempt to the manifest — including failures, with the error message captured
- Read the API key only from .env via python-dotenv — never hardcode it, never print it, never log it
- Comment every function — one line minimum explaining purpose
- Validate --resolution against allowed values (1K/2K/4K) and --aspect-ratio against supported ratios before calling the API

## Guardrails — Never
- Never commit .env or venv/ (already gitignored — don't override this)
- Never overwrite an existing manifest entry — always append
- Never silently overwrite an existing output file — if a filename collision occurs, append an incrementing suffix
- Never add a second model provider without implementing the full BaseImageProvider interface — no shortcuts that bypass the abstraction
- Never call the API in a loop without a delay/retry-aware wrapper — Gemini API rate limits apply, and providers/nano_banana_pro.py should handle 429 responses gracefully (backoff + clear error to the manifest, not a crash)

## End of Session
Update CLAUDE.md with any new decisions made this session.
Update docs/progress.md to reflect what was just built.