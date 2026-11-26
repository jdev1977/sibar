"""Provider adapters behind one interface (T0.5).

Each adapter has ``prepare(model, prompt, api_key) -> Prepared`` and
``parse(response) -> Result`` (see ``base.py``). None of them has been run
against the live API yet: no keys existed when they were written (T0.3).
"""

from runner.providers.anthropic import AnthropicAdapter
from runner.providers.base import Prepared, Result, Tokens
from runner.providers.deepseek import DeepSeekAdapter
from runner.providers.google import GoogleAdapter
from runner.providers.openai import OpenAIAdapter

ADAPTERS = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "google": GoogleAdapter,
    "deepseek": DeepSeekAdapter,
}

__all__ = ["ADAPTERS", "Prepared", "Result", "Tokens", "adapter_for"]


def adapter_for(provider, **options):
    """A new adapter for ``provider`` (as named in models.yaml)."""
    try:
        return ADAPTERS[provider](**options)
    except KeyError:
        raise KeyError(f"no adapter for provider {provider!r}") from None
