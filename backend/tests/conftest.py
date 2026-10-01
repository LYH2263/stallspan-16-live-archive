"""共享测试夹具：用 SQLite 内存库覆盖 Postgres，结构与 seed.py 一致。"""
import os
from datetime import date

# 必须在导入 app.* 之前：app.database 导入时即按 DATABASE_URL 建引擎
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import MarketDay, Pillar, Segment, Vendor


@pytest.fixture
def db_session():
    # StaticPool + 单连接：内存库在 TestClient 的请求线程间共享同一份数据
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with（不触发 lifespan）：lifespan 会对真实 Postgres 建表，测试里改用 SQLite 夹具建表
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db_session):
    """复刻 app/services/seed.py 的种子数据。"""
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db_session.add(day)
    db_session.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0)
    db_session.add(seg)
    db_session.flush()
    db_session.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db_session.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    vendors = [
        ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("老周水果", 5.0, 2),
        ("小美饰品", 2.5, 2), ("大碗面", 6.0, 1), ("手作皮具", 3.5, 3),
        ("巨型舞台车", 12.0, 9),
    ]
    for name, wdt, pri in vendors:
        db_session.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
    db_session.commit()
    return {"day_id": day.id, "segment_id": seg.id}


def vendor_id_by_name(client, name):
    for v in client.get("/api/vendors").json():
        if v["name"] == name:
            return v["id"]
    raise KeyError(name)
