from llm_suite.providers.dummy import DummyProvider
from llm_suite.providers.provider_506 import Provider506
from llm_suite.providers.azure_openai import AzureOpenAIProvider

_REGISTRY = {
    "dummy": DummyProvider,
    "provider_506": Provider506,
    "azure_openai": AzureOpenAIProvider,
}

def make_provider(name: str):
    name = (name or "dummy").strip()
    cls = _REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}. Known: {sorted(_REGISTRY.keys())}")
    return cls()