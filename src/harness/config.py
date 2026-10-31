"""Environment configuration. The model is always read from HARNESS_MODEL, never hardcoded."""

import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

# Context window of Databricks' gpt-oss endpoints (Databricks docs: 128K tokens).
DATABRICKS_MAX_INPUT_TOKENS = 128_000


def load_env() -> None:
    """Load .env into os.environ. Variables already set in the shell take precedence."""
    load_dotenv(override=False)


def get_model_name() -> str:
    """Return the `provider:model` string from HARNESS_MODEL, or fail loudly."""
    model = os.environ.get("HARNESS_MODEL", "").strip()
    if not model:
        raise RuntimeError(
            "HARNESS_MODEL is not set. Copy .env.example to .env and set it, "
            "e.g. HARNESS_MODEL=databricks:databricks-gpt-oss-120b"
        )
    return model


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set (needed for the selected HARNESS_MODEL provider).")
    return value


def get_chat_model() -> BaseChatModel:
    """Build the chat model named by HARNESS_MODEL.

    `databricks:<endpoint>` calls a Databricks Model Serving endpoint through its
    OpenAI-compatible Chat Completions API. Databricks does not serve the Responses
    API, so it is switched off. `azure_v1:<deployment>` uses the Azure OpenAI v1
    Chat Completions API with no dated API version. Other providers go to init_chat_model.
    """
    name = get_model_name()
    provider, sep, model = name.partition(":")
    if not sep or not provider or not model:
        raise RuntimeError(f"HARNESS_MODEL must look like 'provider:model', got {name!r}.")
    if provider == "azure_v1":
        endpoint = _require_env("AZURE_OPENAI_ENDPOINT").rstrip("/") + "/"
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path != "/openai/v1/":
            raise RuntimeError("AZURE_OPENAI_ENDPOINT must be an HTTPS /openai/v1/ base URL without query parameters.")
        return ChatOpenAI(
            model=model,  # Azure deployment name, not the underlying model identifier
            base_url=endpoint,
            api_key=_require_env("AZURE_OPENAI_API_KEY"),
            use_responses_api=False,
            # Conservative harness context budget for a deployment with a custom name.
            # This is not the Azure deployment's TPM quota or a claim about model capacity.
            profile={"max_input_tokens": int(os.environ.get("HARNESS_MAX_INPUT_TOKENS") or 128_000)},
        )
    if provider == "databricks":
        host = _require_env("DATABRICKS_HOST").rstrip("/")
        return ChatOpenAI(
            model=model,
            base_url=f"{host}/serving-endpoints",
            api_key=_require_env("DATABRICKS_TOKEN"),
            use_responses_api=False,
            # Without a profile, deepagents' summarization falls back to a 170,000-token trigger, above
            # gpt-oss's 128K window, so it would never fire. With it: summarize at 85% of the window.
            profile={"max_input_tokens": int(os.environ.get("HARNESS_MAX_INPUT_TOKENS") or DATABRICKS_MAX_INPUT_TOKENS)},
        )
    return init_chat_model(name)
