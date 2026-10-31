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


def test_azure_v1_uses_deployment_and_exact_base_url(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL", "azure_v1:gpt-5-mini-group4")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.cognitiveservices.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-test-key")
    model = get_chat_model()
    assert model.model_name == "gpt-5-mini-group4"
    assert model.openai_api_base == "https://example.cognitiveservices.azure.com/openai/v1/"
    assert model.use_responses_api is False
    assert model.profile["max_input_tokens"] == 128_000
    assert "api-version" not in str(model.client._client.base_url)
    assert model.bind_tools([{"name": "lookup", "description": "Read a record", "parameters": {"type": "object", "properties": {}}}])


@pytest.mark.parametrize("missing", ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"])
def test_azure_v1_requires_credentials(monkeypatch, missing):
    monkeypatch.setenv("HARNESS_MODEL", "azure_v1:gpt-5-mini-group4")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.cognitiveservices.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-test-key")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        get_chat_model()


@pytest.mark.parametrize("endpoint", ["http://example.com/openai/v1/", "https://example.com/", "https://example.com/openai/v1/?api-version=old"])
def test_azure_v1_refuses_incompatible_endpoint(monkeypatch, endpoint):
    monkeypatch.setenv("HARNESS_MODEL", "azure_v1:gpt-5-mini-group4")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", endpoint)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-test-key")
    with pytest.raises(RuntimeError, match="HTTPS"):
        get_chat_model()
