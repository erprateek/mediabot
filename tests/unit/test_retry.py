"""
tests/unit/test_retry.py
"""

import pytest
import requests

from src.services.retry import call_with_retries, retryable


class TestCallWithRetries:
    def test_returns_on_first_success(self):
        calls = []
        result = call_with_retries(lambda: calls.append(1) or "ok")
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_transient_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("src.services.retry.time.sleep", lambda _: None)
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise requests.exceptions.Timeout("blip")
            return "recovered"

        assert call_with_retries(flaky, retries=3) == "recovered"
        assert attempts["n"] == 3

    def test_raises_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setattr("src.services.retry.time.sleep", lambda _: None)
        attempts = {"n": 0}

        def always_fails():
            attempts["n"] += 1
            raise requests.exceptions.ConnectionError("down")

        with pytest.raises(requests.exceptions.ConnectionError):
            call_with_retries(always_fails, retries=3)
        assert attempts["n"] == 3

    def test_non_transient_raises_immediately(self):
        attempts = {"n": 0}

        def bad_type():
            attempts["n"] += 1
            raise ValueError("not transient")

        with pytest.raises(ValueError):
            call_with_retries(bad_type, retries=5)
        assert attempts["n"] == 1

    def test_backoff_is_exponential(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr("src.services.retry.time.sleep", sleeps.append)

        def always_timeout():
            raise requests.exceptions.Timeout("t")

        with pytest.raises(requests.exceptions.Timeout):
            call_with_retries(always_timeout, retries=4, backoff=0.5)
        assert sleeps == [0.5, 1.0, 2.0]

    def test_passes_through_args_and_kwargs(self):
        result = call_with_retries(lambda a, b=0: a + b, 2, b=3, retries=2)
        assert result == 5


class TestRetryableDecorator:
    def test_decorator_retries(self, monkeypatch):
        monkeypatch.setattr("src.services.retry.time.sleep", lambda _: None)
        attempts = {"n": 0}

        @retryable(retries=3)
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise requests.exceptions.ConnectionError("x")
            return "done"

        assert flaky() == "done"
        assert attempts["n"] == 2

    def test_decorator_preserves_function_name(self):
        @retryable()
        def my_fetch():
            pass

        assert my_fetch.__name__ == "my_fetch"
