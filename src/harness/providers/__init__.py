from harness.providers.base import LLMProvider
from harness.providers.openai_provider import OpenAIProvider


def make_provider(settings, model=None, reasoning_effort=None, temperature=None) -> LLMProvider:
    effort = reasoning_effort if reasoning_effort is not None else settings.reasoning_effort
    match settings.provider:
        case "openai" | "azure":
            return OpenAIProvider(
                api_key=settings.api_key,
                base_url=settings.endpoint,
                model=model or settings.model,
                reasoning_effort=effort,
                temperature=temperature,
            )
        case _:
            raise ValueError(f"Unknown provider: {settings.provider}")
