"""Text-only prompt refinement: clarifying questions + synthesis, via a lightweight
Gemini text model (config: refiner_model_string). Deliberately NOT a BaseImageProvider
subclass — refinement isn't image generation and doesn't fit that interface (no
aspect_ratio/resolution/output_dir). Still lives under providers/ per CLAUDE.md's
guardrail that google-genai is never called outside providers/."""

import os

from google import genai
from google.genai import types
from pydantic import BaseModel
from rich.console import Console

from utils.retry import call_with_retry

console = Console()


class ClarifyingQuestion(BaseModel):
    """One clarifying question with a recommended default answer (Enter accepts it)."""

    question: str
    recommended_answer: str


class QuestionsResponse(BaseModel):
    """Structured-output schema for the clarifying-questions call (response_schema)."""

    questions: list[ClarifyingQuestion]


_QUESTIONS_PROMPT = """You are a prompt-refinement assistant for an AI image generation \
pipeline for MyYogaTeacher (MYT). Given the user's raw prompt, the campaign name, the \
filenames of the reference images that will be used (filenames are often informative — \
e.g. a pose name), and the brand guide below, identify important ambiguities in the \
prompt that would meaningfully change the generated image if left unspecified.

Return at most {max_questions} clarifying questions. Each question MUST include a \
recommended_answer: a sensible, on-brand default an experienced MYT marketer would pick, \
written so the user can accept it by pressing Enter. If the prompt is already \
sufficiently specific and unambiguous, return an empty questions list — do not invent \
questions for the sake of it.

Campaign: {campaign}
Reference image filenames:
{reference_filenames}

Brand guide:
{brand_guide}

User's prompt:
{user_prompt}"""

_SYNTHESIS_PROMPT = """Combine the original image-generation prompt below with the \
following clarifying question/answer pairs into ONE polished, single flowing paragraph \
suitable to send directly to an image-generation model. Do not use bullet points, \
headers, or labeled sections — write natural-language prose. Preserve every concrete \
detail from both the original prompt and the answers; do not drop or contradict any of \
them.
{guide_instruction}
Campaign: {campaign}

Original prompt:
{user_prompt}

Clarifying Q&A:
{qa_block}"""

_GUIDE_INSTRUCTION = """
Also apply the phrasing conventions below wherever they fit naturally — they make the \
prompt unambiguous for the image model (e.g. naming the medium, lighting, and camera \
style explicitly, using hex codes for color, stating exact counts, and including \
relevant negatives). Do not force in a convention that doesn't apply to this prompt, \
and never contradict the original prompt or the Q&A to satisfy one.

Prompting guide:
{prompting_guide}
"""


class PromptRefiner:
    """Two lightweight text-only calls: clarifying questions, then paragraph synthesis."""

    def __init__(self, model_name: str) -> None:
        """Store the refiner model name and build the google-genai client from GEMINI_API_KEY."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set. Add it to .env before refining prompts.")
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def generate_questions(
        self,
        user_prompt: str,
        campaign: str,
        reference_filenames: list[str],
        brand_guide: str,
        max_questions: int,
    ) -> list[ClarifyingQuestion]:
        """Ask the refiner model for up to max_questions clarifying questions (may be empty).

        Raises on unrecoverable API failure — callers decide the fallback policy.
        """
        prompt_text = _QUESTIONS_PROMPT.format(
            max_questions=max_questions,
            campaign=campaign,
            reference_filenames="\n".join(f"- {f}" for f in reference_filenames) or "(none)",
            brand_guide=brand_guide or "(no brand guide content)",
            user_prompt=user_prompt,
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuestionsResponse,
        )
        response = call_with_retry(
            lambda: self.client.models.generate_content(
                model=self.model_name, contents=[prompt_text], config=config
            ),
            console=console,
        )
        parsed = response.parsed or QuestionsResponse.model_validate_json(response.text)
        return parsed.questions[:max_questions]

    def synthesize_prompt(
        self, user_prompt: str, campaign: str, qa: list[dict], prompting_guide: str = ""
    ) -> str:
        """Merge the raw prompt + answered Q&A into one polished single-paragraph prompt.

        prompting_guide (docs/prompting-guide.md content, if provided) is applied as
        phrasing conventions for the model to fold in, not new content to ask about.

        Raises on unrecoverable API failure — callers decide the fallback policy.
        """
        qa_block = "\n".join(f"Q: {item['question']}\nA: {item['answer']}" for item in qa)
        guide_instruction = _GUIDE_INSTRUCTION.format(prompting_guide=prompting_guide) if prompting_guide else ""
        prompt_text = _SYNTHESIS_PROMPT.format(
            campaign=campaign, user_prompt=user_prompt, qa_block=qa_block, guide_instruction=guide_instruction
        )
        response = call_with_retry(
            lambda: self.client.models.generate_content(model=self.model_name, contents=[prompt_text]),
            console=console,
        )
        return response.text.strip()
