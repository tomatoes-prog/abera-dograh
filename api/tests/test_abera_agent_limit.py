import pytest

from api.db.workflow_client import WorkflowClient
from api.errors.abera import AgentLimitExceeded


class CountSession:
    def __init__(self, count):
        self.count = count
        self.locked = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, statement, parameters):
        assert "pg_advisory_xact_lock" in str(statement)
        assert parameters == {"org_id": 7}
        self.locked = True

    async def scalar(self, _statement):
        assert self.locked
        return self.count

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_managed_agent_limit_is_checked_under_transaction_lock(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    monkeypatch.setenv("ABERA_MAX_AGENTS", "2")
    session = CountSession(count=2)
    client = WorkflowClient.__new__(WorkflowClient)
    client.async_session = lambda: session

    with pytest.raises(AgentLimitExceeded, match="2 agentes"):
        await client.create_workflow("third", {}, user_id=1, organization_id=7)

    assert session.locked
    assert session.rolled_back
