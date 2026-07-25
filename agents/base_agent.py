import base64
import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_MODEL = "claude-sonnet-5"
FEEDBACK_MODEL = "claude-haiku-4-5"
# Model for the initial plan + initial write only (Outer's first inner call).
# Revisions and reviewers keep their own models.
INITIAL_DRAFT_MODEL = "claude-opus-5"

# The Sonnet 5 / Opus 5 family runs adaptive thinking on by default when the
# `thinking` field is omitted, which would (a) place a thinking block at
# content[0] and (b) spend output tokens on reasoning. We keep the pipeline's
# behavior controlled by disabling thinking on every call. Text extraction also
# tolerates a leading non-text block defensively.
_THINKING_DISABLED = {"type": "disabled"}

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
        (e.g. thinking) block. Falls back to content[0].text."""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return response.content[0].text

    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = None,
        max_tokens: int = 8192,
    ) -> str:
        """Send a prompt to Claude and return the text response."""
        response = self.client.messages.create(
            model=model or self.model,
            max_tokens=max_tokens,
            thinking=_THINKING_DISABLED,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return self._first_text(response)

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
        response = self.client.messages.create(
            model=model or self.model,
            max_tokens=max_tokens,
            thinking=_THINKING_DISABLED,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        return self._first_text(response)
