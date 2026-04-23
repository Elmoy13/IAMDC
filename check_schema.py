import asyncio
import ssl

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    e = create_async_engine(
        settings.database_url,
        connect_args={"prepared_statement_cache_size": 0, "ssl": ctx},
    )
    async with e.connect() as c:
        for table in ["channels", "contacts", "conversations", "messages"]:
            q = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"
            r = await c.execute(text(q))
            print(f"\n=== {table} ===")
            for row in r:
                print(f"  {row[0]}: {row[1]}")
    await e.dispose()


asyncio.run(main())
