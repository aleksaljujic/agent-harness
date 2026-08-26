from harness.providers.base import LLMProvider
from harness.providers.openai_provider import OpenAIProvider

def make_provider(settings, model = None) -> LLMProvider:
    match settings.provider:
        case "openai" | "azure":
            return OpenAIProvider(
                api_key=settings.api_key,
                base_url=settings.endpoint,
                model=model or settings.model
            )
        case _:
            raise ValueError(f"Unknown provider: {settings.provider}")