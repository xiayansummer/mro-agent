from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    # aiomysql 的 AsyncAdapt 连接 ping() 签名与 SQLAlchemy pre_ping 不兼容
    # (TypeError: ping() missing 'reconnect'),无法用 pool_pre_ping=True。
    # 改用短 pool_recycle:在连接被公网 NAT / MySQL 空闲超时(常 300-600s)掐断
    # 之前就主动回收,规避间歇性 "MySQL server has gone away"。
    pool_recycle=240,
    pool_pre_ping=False,
    # 每条连接钉死 session 时区为 UTC:让 DB 端 CURRENT_TIMESTAMP / NOW() /
    # ON UPDATE 始终按 UTC 写入,与应用 datetime.utcnow() 对齐,不再依赖 MySQL
    # 主机的 SYSTEM 时区(当前恰好 UTC,但迁到 CST 主机会立刻偏 8h)。
    connect_args={"init_command": "SET time_zone = '+00:00'"},
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
