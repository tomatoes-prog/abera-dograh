import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.services.abera.maintenance import wait_for_writes
from api.services.abera.readiness import check_ui, check_workers, orchestrator_heartbeat


def test_background_writes_wait_for_the_startup_gate_to_open():
    redis = Mock(get=AsyncMock(side_effect=[b"1", b"1", None]))
    with patch(
        "api.services.abera.maintenance.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        asyncio.run(wait_for_writes(redis))
    assert redis.get.await_count == 3
    assert sleep.await_count == 2


def test_unavailable_redis_never_authorizes_background_writes():
    redis = Mock(get=AsyncMock(side_effect=ConnectionError("unavailable")))
    with pytest.raises(ConnectionError):
        asyncio.run(wait_for_writes(redis))


@pytest.mark.parametrize(
    "mode,method,paused,unavailable,expected",
    [
        ("abera", "POST", True, False, 503),
        ("abera", "POST", False, True, 503),
        ("abera", "POST", False, False, 200),
        ("abera", "GET", True, False, 200),
        ("oss", "POST", True, False, 200),
    ],
)
def test_api_startup_gate_preserves_read_access_and_fails_closed(
    mode, method, paused, unavailable, expected
):
    # Execute the actual middleware body without importing DB connections/app startup.
    tree = ast.parse((Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8"))
    function = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "managed_startup_writes"
    )
    function.decorator_list = []
    function.returns = None
    for argument in function.args.args:
        argument.annotation = None
    redis = Mock(
        get=AsyncMock(
            side_effect=ConnectionError() if unavailable else None, return_value=paused
        )
    )
    namespace = {
        "DEPLOYMENT_MODE": mode,
        "get_arq_redis": AsyncMock(return_value=redis),
        "JSONResponse": lambda **kwargs: SimpleNamespace(
            status_code=kwargs["status_code"]
        ),
    }
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]),
            "<managed_startup_writes>",
            "exec",
        ),
        namespace,
    )
    next_handler = AsyncMock(return_value=SimpleNamespace(status_code=200))
    result = asyncio.run(
        namespace["managed_startup_writes"](
            SimpleNamespace(method=method), next_handler
        )
    )
    assert result.status_code == expected
    assert next_handler.await_count == (1 if expected == 200 else 0)


@pytest.mark.parametrize("values", [[None, None], [b"live", None], [None, b"live"], []])
def test_missing_worker_never_admits_service(values):
    with pytest.raises(RuntimeError, match="heartbeat"):
        asyncio.run(check_workers(Mock(mget=AsyncMock(return_value=values))))


def test_both_live_workers_are_required():
    asyncio.run(check_workers(Mock(mget=AsyncMock(return_value=[b"live", b"ready"]))))


def test_heartbeat_starts_only_after_subscription_and_is_removed_on_failure():
    async def scenario():
        redis = Mock(set=AsyncMock(), delete=AsyncMock())
        ready = asyncio.Event()
        task = asyncio.create_task(orchestrator_heartbeat(redis, ready))
        await asyncio.sleep(0)
        redis.set.assert_not_called()
        ready.set()
        await asyncio.sleep(0)
        redis.set.assert_awaited_once_with("abera:health:orchestrator", "ready", ex=15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        redis.delete.assert_awaited_once_with("abera:health:orchestrator")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,body", [(503, b"<html>failed"), (200, b'{"error":true}'), (404, b"<html>")]
)
def test_ui_response_must_be_a_successful_page(status, body):
    response = Mock(status=status, read=Mock(return_value=body))
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    with patch("api.services.abera.readiness.urlopen", return_value=context):
        with pytest.raises(RuntimeError, match="login"):
            check_ui()


def test_login_page_probe_has_a_bounded_fixed_destination():
    response = Mock(status=200, read=Mock(return_value=b"<!DOCTYPE html><html>"))
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    with patch("api.services.abera.readiness.urlopen", return_value=context) as fetch:
        check_ui()
        fetch.assert_called_once_with("http://ui:3010/auth/login", timeout=5)
