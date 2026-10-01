import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import MarketDay, Pillar, Segment, Vendor
from app.services.seed import seed_if_empty


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    seed_if_empty(db)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    # 不进入 with：跳过 lifespan（避免触碰 postgres 引擎），表已由 fixture 建好。
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seed_state():
    """种子数据的口径锚点（与 seed.py 保持一致）。"""
    return {
        "segment_width": 30.0,
        "dan_van": {"id": 5, "name": "大碗面", "width": 6.0},
        "fruit": {"id": 3, "name": "老周水果", "width": 5.0},
        "stage_truck": {"id": 7, "name": "巨型舞台车", "width": 12.0},
    }
