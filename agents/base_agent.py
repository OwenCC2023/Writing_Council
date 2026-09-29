import base64
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_MODEL = "claude-sonnet-5-5"
FEEDBACK_MODEL = "claude-haiku-4-5"
# Model for the initial plan + initial write only (Outer's first inner call).
# Revisions and reviewers keep their own models.
INITIAL_DRAFT_MODEL = "claude-opus-5-5"

# Output ceiling. Prose runs ~1.4 tokens per word; the ceiling keeps a runaway
# target from requesting more than the API will return.
_TOKENS_PER_WORD = 1.4
MAX_OUTPUT_TOKENS = 32000


def max_tokens_for(target_length: str, floor: int) -> int:
    """Derive an output budget from a target length like "8,000 words".

    Returns `floor` when no count can be parsed, so an unrecognised target
    behaves exactly as it does today. Never returns less than `floor`.
    """
    match = re.search(r"[\d,]+", target_length or "")
    if not match:
        return floor
    digits = match.group().replace(",", "")
    if not digits:
        return floor
    words = int(digits)
    return max(floor, min(int(words * _TOKENS_PER_WORD), MAX_OUTPUT_TOKENS))

# Thinking is not optional on the 5.5 family: `{"type": "disabled"}` is a 400 on
# both Opus 5.5 and Sonnet 5.5, so effort is the only control. Opus 5.5's API
# default is `medium` (one level below Opus 5's `high`); it is set explicitly so
# the default can't move under us. Sonnet 5.5 runs at `low`, where it skips
# thinking on most simple requests. Any other model (Haiku reviewers, a test's
# override) keeps thinking disabled, as before. Text extraction reads blocks by
# type, since a response can open with a thinking block.
_EFFORT_BY_MODEL = {
    "claude-opus-5-5": "medium",
    "claude-sonnet-5-5": "low",
}
_THINKING_DISABLED = {"type": "disabled"}

# Effort for the Sonnet calls whose job is counting or synthesis rather than prose:
# tallying one construction across a whole manuscript, holding a per-section density
# band, and merging several reviewers into one fix list without dropping a finding.
# `low` skips thinking on most requests, and those are the calls that need it.
ANALYSIS_EFFORT = "medium"

# Thinking counts toward max_tokens even though its text isn't returned, so a
# budget sized for the prose alone would cut the story off. Headroom is only
# billed when used.
THINKING_HEADROOM = 16000

# On a safety-classifier decline, re-run the request on the model Anthropic
# recommends for that refusal category, inside the same call. A false positive
# on dark fiction otherwise kills a run minutes and dollars in.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class RefusalError(RuntimeError):
    """The model (and any fallback) declined the request."""


def _request_params(model: str, max_tokens: int, effort: str = None) -> dict:
    """Model-specific thinking / effort / fallback settings for one call.

    `effort` overrides the model's default level, and is ignored on a model with
    no `_EFFORT_BY_MODEL` entry — those run thinking-disabled, where an effort
    field is at best meaningless (Haiku 4.5 rejects it).
    """
    default = _EFFORT_BY_MODEL.get(model)
    if default is None:
        return {"max_tokens": max_tokens, "thinking": _THINKING_DISABLED}
    effort = effort or default
    return {
        "max_tokens": max_tokens + THINKING_HEADROOM,
        "output_config": {"effort": effort},
        "betas": [_FALLBACK_BETA],
        "extra_body": {"fallbacks": "default"},
    }

_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class BaseAgent:
    """Shared Anthropic client and call logic for all Writing Council agents."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @staticmethod
    def _first_text(response) -> str:
        """Return the first text block's text, tolerating a leading non-text
        (e.g. thinking) block. Raises RefusalError on a classifier decline,
        whose content may hold no text at all."""
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) or "unspecified"
            raise RefusalError(
                f"{getattr(response, 'model', 'model')} declined the request "
                f"(refusal category: {category})"
            )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return response.content[0].text

    def _send(self, model: str, max_tokens: int, system_prompt: str, content,
              effort: str = None) -> str:
        """Stream one request and return its text. Streaming because the SDK
        refuses a non-streaming call whose max_tokens could run past ten
        minutes (~21k tokens), which thinking headroom on a long write crosses."""
        with self.client.beta.messages.stream(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            **_request_params(model, max_tokens, effort),
        ) as stream:
            response = stream.get_final_message()
        return self._first_text(response)

    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = None,
        max_tokens: int = 8192,
        effort: str = None,
    ) -> str:
        """Send a prompt to Claude and return the text response."""
        return self._send(model or self.model, max_tokens, system_prompt, user_prompt,
                          effort=effort)

    def _call_claude_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        images: str | list,
        model: str = None,
        max_tokens: int = 8192,
    ) -> str:
        """Send a multimodal prompt (one or more images + text) to Claude and return
        the text response.

        Args:
            images: A file path or http/https URL, or a list of such strings.
        """
        if isinstance(images, str):
            images = [images]

        image_blocks = []
        for image in images:
            if image.startswith(("http://", "https://")):
                image_blocks.append({
                    "type": "image",
                    "source": {"type": "url", "url": image},
                })
            else:
                path = Path(image)
                media_type = _IMAGE_MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
                with open(path, "rb") as fh:
                    data = base64.standard_b64encode(fh.read()).decode("utf-8")
                image_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })

        content = [*image_blocks, {"type": "text", "text": user_prompt}]
        return self._send(model or self.model, max_tokens, system_prompt, content)
