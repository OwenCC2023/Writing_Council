import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_MODEL = "claude-sonnet-4-6"
FEEDBACK_MODEL = "claude-haiku-4-5-20251001"


class BaseAgent:
    """Shared Anthropic client and call logic for all Writing Council agents."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

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
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
