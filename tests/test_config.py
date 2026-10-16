import pytest
from langchain_openai import ChatOpenAI

from harness.config import get_chat_model, get_model_name


def test_model_name_required(monkeypatch):
    monkeypatch.delenv("HARNESS_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="HARNESS_MODEL"):
        get_model_name()


def test_model_name_from_env(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL", "databricks:some-endpoint")
    assert get_model_name() == "databricks:some-endpoint"


def test_malformed_model_name(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL", "no-provider-here")
    with pytest.raises(RuntimeError, match="provider:model"):
        get_chat_model()


def test_databricks_maps_to_chat_completions(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL", "databricks:some-endpoint")
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    model = get_chat_model()
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "some-endpoint"
    assert model.openai_api_base == "https://example.cloud.databricks.com/serving-endpoints"
    assert model.use_responses_api is False


@pytest.mark.parametrize("missing", ["DATABRICKS_HOST", "DATABRICKS_TOKEN"])
def test_databricks_requires_host_and_token(monkeypatch, missing):
    monkeypatch.setenv("HARNESS_MODEL", "databricks:some-endpoint")
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        get_chat_model()


def test_deepagents_importable():
    from deepagents import create_deep_agent

    assert callable(create_deep_agent)
