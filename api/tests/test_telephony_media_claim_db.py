"""A signed media URL can create only one session, even during a race."""

import asyncio
import uuid

from sqlalchemy import delete

from api.db import db_client
from api.db.models import OrganizationModel, UserModel, WorkflowModel, WorkflowRunModel
from api.tests.test_campaign_call_dispatcher import sessions


async def test_media_claim_is_atomic_and_scoped(sessions):
    async with sessions() as session:
        org = OrganizationModel(provider_id=f"media-claim-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = UserModel(provider_id=f"media-claim-{uuid.uuid4().hex}", selected_organization_id=org.id)
        session.add(user)
        await session.flush()
        workflow = WorkflowModel(name="media-claim", user_id=user.id, organization_id=org.id)
        session.add(workflow)
        await session.flush()
        run = WorkflowRunModel(name="media-claim", workflow_id=workflow.id, mode="twilio", state="initialized", is_completed=False)
        session.add(run)
        await session.commit()
    try:
        assert not await db_client.claim_telephony_media(run.id, workflow.id, org.id + 1000000)
        claims = await asyncio.gather(*(db_client.claim_telephony_media(run.id, workflow.id, org.id) for _ in range(5)))
        assert claims.count(True) == 1
        assert claims.count(False) == 4
    finally:
        async with sessions() as session:
            await session.execute(delete(WorkflowRunModel).where(WorkflowRunModel.id == run.id))
            await session.execute(delete(WorkflowModel).where(WorkflowModel.id == workflow.id))
            await session.execute(delete(UserModel).where(UserModel.id == user.id))
            await session.execute(delete(OrganizationModel).where(OrganizationModel.id == org.id))
            await session.commit()
