from typing import Any, Dict, List
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.constants import ABERA_DB_POOL_SIZE, DATABASE_URL, DEPLOYMENT_MODE


@lru_cache(maxsize=1)
def _managed_engine():
    # API, ARQ, orchestrator and optional ARI each get at most two connections.
    # Clients in one process share the pool, leaving headroom for admin tasks
    # within the tenant's PostgreSQL connection limit of ten.
    return create_async_engine(DATABASE_URL, pool_pre_ping=True,
                               pool_size=ABERA_DB_POOL_SIZE, max_overflow=0,
                               pool_timeout=15, pool_recycle=300)


class BaseDBClient:
    def __init__(self):
        self.engine = (_managed_engine() if DEPLOYMENT_MODE == "abera"
                       else create_async_engine(DATABASE_URL, pool_pre_ping=True))
        self.async_session = async_sessionmaker(bind=self.engine)

    async def execute_raw_query(
        self, query: str, params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a raw SQL query and return results as a list of dictionaries.

        Args:
            query: The SQL query to execute
            params: Optional dictionary of query parameters

        Returns:
            List of dictionaries containing the query results
        """
        async with self.async_session() as session:
            result = await session.execute(text(query), params or {})
            rows = result.fetchall()
            if rows:
                # Convert rows to dictionaries
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            return []
