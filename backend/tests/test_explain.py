"""Tests of the check explanation. No network: the Anthropic client is always faked."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.explain import service
from app.explain.service import build_payload, explain, router

CHECK: dict[str, Any] = {
    "check_id": "c1",
    "verdict": "red",
    "score": 90,
    "headline_ru": "Реквизиты поставщика изменились",
    "headline": "Реквизиты поставщика изменились",
    "signals": [
        {
            "rule_id": "amount_anomaly",
            "severity": "amplifier",
            "reason": "Сумма в 5 раз больше обычной.",
            "reason_ru": "Сумма в 5 раз больше обычной.",
        },
        {
            "rule_id": "iik_changed",
            "severity": "primary",
            "reason": "У поставщика сменился ИИК.",
            "reason_ru": "У поставщика сменился ИИК.",
        },
        {"rule_id": "bik_changed", "severity": "amplifier", "reason": "Сменился банк."},
        {"rule_id": "purpose_urgent", "severity": "info", "reason": "Слово «срочно» в назначении."},
    ],
    "comparison": [
        {
            "field": "iik",
            "in_invoice": "KZ246010005016525808",
            "in_history": "KZ111111111111111111",
            "differs": True,
        },
        {"field": "amount", "in_invoice": "1 214 285 ₸", "in_history": None, "differs": False},
    ],
    "next_action": {"text": "Позвоните поставщику по номеру из договора.", "primary": "postpone"},
    "analyst_details": {"bcc_account": {"owner_name": "ТОО Секрет", "owner_bin": "123456789012"}},
}
TEMPLATE_RU = (
    "Реквизиты поставщика изменились. У поставщика сменился ИИК. Сумма в 5 раз больше обычной. "
    "Сменился банк. Позвоните поставщику по номеру из договора."
)


class FakeClient:
    """Stands in for ``anthropic.Anthropic().with_options(...)``."""

    def __init__(
        self, text: str = "", stop_reason: str = "end_turn", error: Exception | None = None
    ):
        self.text = text
        self.stop_reason = stop_reason
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        block = SimpleNamespace(type="text", text=self.text)
        thinking = SimpleNamespace(type="thinking", thinking="hidden")
        return SimpleNamespace(stop_reason=self.stop_reason, content=[thinking, block])


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    service._cache.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(service, "load_env_file", lambda *a, **k: None)
    yield
    service._cache.clear()


def use_client(monkeypatch: pytest.MonkeyPatch, client: FakeClient | None) -> None:
    monkeypatch.setattr(service, "_make_client", lambda: client)


def test_template_without_key() -> None:
    result = explain(CHECK, "ru")
    assert result.source == "template"
    assert result.warnings == ["no_api_key"]
    assert result.text == TEMPLATE_RU


def test_template_uses_localized_fields_and_limits_reasons() -> None:
    check = {
        "headline": "Details changed",
        "headline_ru": "Реквизиты изменились",
        "signals": [
            {"severity": "info", "reason": "d", "reason_ru": "г"},
            {"severity": "block", "reason": "a", "reason_ru": "а"},
            {"severity": "primary", "reason": "b", "reason_ru": "б"},
            {"severity": "amplifier", "reason": "c", "reason_ru": "в"},
        ],
        "next_action": {"text": "Call them", "text_ru": "Позвоните"},
    }
    assert explain(check, "en").text == "Details changed. a. b. c. Call them."


def test_template_empty_check_is_not_empty() -> None:
    assert explain({}, "kk").text
    assert explain({}, "xx").text == service.EMPTY_TEXT["ru"]  # unknown language -> ru


def test_payload_is_whitelisted() -> None:
    payload = build_payload(CHECK)
    assert set(payload) == {"verdict", "headline", "signals", "next_action_text", "comparison"}
    assert "analyst_details" not in str(payload)
    assert "Секрет" not in str(payload)
    assert set(payload["signals"][0]) == {"rule_id", "reason", "severity"}
    assert payload["comparison"][0]["differs"] is True


def test_claude_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient("**Сменился ИИК** поставщика. Позвоните по номеру из договора.")
    use_client(monkeypatch, fake)
    result = explain(CHECK, "ru")
    assert result.source == "claude"
    assert result.warnings == []
    assert result.text == "Сменился ИИК поставщика. Позвоните по номеру из договора."  # no markdown
    call = fake.calls[0]
    assert call["max_tokens"] == 600
    assert call["output_config"] == {"effort": "low"}
    assert "Russian" in call["system"]
    assert call["messages"][0]["role"] == "user"
    assert "analyst_details" not in call["messages"][0]["content"]
    assert call["model"] == "claude-haiku-5-5"


def test_model_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPLAIN_AI_MODEL", "claude-test")
    fake = FakeClient("Ок.")
    use_client(monkeypatch, fake)
    explain(CHECK, "en")
    assert fake.calls[0]["model"] == "claude-test"


def test_refusal_falls_back_to_template(monkeypatch: pytest.MonkeyPatch) -> None:
    use_client(monkeypatch, FakeClient("sorry", stop_reason="refusal"))
    result = explain(CHECK, "ru")
    assert result.source == "template"
    assert result.warnings == ["refusal_or_empty"]
    assert result.text == TEMPLATE_RU


def test_empty_answer_falls_back_to_template(monkeypatch: pytest.MonkeyPatch) -> None:
    use_client(monkeypatch, FakeClient(""))
    assert explain(CHECK, "ru").source == "template"


def test_hallucinated_number_falls_back_to_template(monkeypatch: pytest.MonkeyPatch) -> None:
    use_client(monkeypatch, FakeClient("Платёж на 9 876 543 тенге нужно задержать."))
    result = explain(CHECK, "ru")
    assert result.source == "template"
    assert result.warnings == ["number_not_in_check"]
    use_client(monkeypatch, FakeClient("Новый ИИК KZ999999999999999999 подозрителен."))
    assert explain(CHECK, "ru").source == "template"


def test_numbers_from_the_check_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    use_client(monkeypatch, FakeClient("Платёж на 1 214 285 тенге пойдёт на KZ246010005016525808."))
    assert explain(CHECK, "ru").source == "claude"


@pytest.mark.parametrize(
    ("error", "warning"),
    [
        (
            anthropic.RateLimitError(
                "limit",
                response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                body=None,
            ),
            "rate_limited",
        ),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")),
            "connection_error",
        ),
        (
            anthropic.APIStatusError(
                "boom",
                response=httpx.Response(500, request=httpx.Request("POST", "http://x")),
                body=None,
            ),
            "api_error_500",
        ),
    ],
)
def test_sdk_errors_fall_back_to_template(
    monkeypatch: pytest.MonkeyPatch, error: Exception, warning: str
) -> None:
    use_client(monkeypatch, FakeClient(error=error))
    result = explain(CHECK, "ru")
    assert result.source == "template"
    assert result.warnings == [warning]
    assert result.text == TEMPLATE_RU
    assert not service._cache  # an error is never cached


def test_cache_by_payload_and_language(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient("Сменился ИИК.")
    use_client(monkeypatch, fake)
    first = explain(CHECK, "ru")
    second = explain({**CHECK, "check_id": "other", "score": 1}, "ru")  # not part of the payload
    assert first == second
    assert len(fake.calls) == 1
    explain(CHECK, "en")  # other language -> new request
    assert len(fake.calls) == 2
    explain({**CHECK, "headline": "Другое", "headline_ru": "Другое"}, "ru")  # other content
    assert len(fake.calls) == 3


def test_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "CACHE_SIZE", 2)
    use_client(monkeypatch, FakeClient("Ок."))
    for i in range(5):
        explain({"headline": f"h{i}"}, "ru")
    assert len(service._cache) == 2


def test_endpoint() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    for path in ("/api/explain", "/api/explain/"):
        response = client.post(path, json={"check": CHECK, "lang": "ru"})
        assert response.status_code == 200
        assert response.json() == {
            "text": TEMPLATE_RU,
            "source": "template",
            "warnings": ["no_api_key"],
        }
    assert client.post("/api/explain", json={"lang": "ru"}).status_code == 422
