"""Environment configuration. The model is always read from HARNESS_MODEL, never hardcoded."""

import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


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
        raise RuntimeError(f"{name} is not set (needed for HARNESS_MODEL=databricks:...).")
    return value


def get_chat_model() -> BaseChatModel:
    """Build the chat model named by HARNESS_MODEL.

    `databricks:<endpoint>` calls a Databricks Model Serving endpoint through its
    OpenAI-compatible Chat Completions API. Databricks does not serve the Responses
    API, so it is switched off. Any other `provider:model` goes to init_chat_model.
    """
    name = get_model_name()
    provider, sep, model = name.partition(":")
    if not sep or not provider or not model:
        raise RuntimeError(f"HARNESS_MODEL must look like 'provider:model', got {name!r}.")
    if provider == "databricks":
        host = _require_env("DATABRICKS_HOST").rstrip("/")
        return ChatOpenAI(
            model=model,
            base_url=f"{host}/serving-endpoints",
            api_key=_require_env("DATABRICKS_TOKEN"),
            use_responses_api=False,
        )
    return init_chat_model(name)
