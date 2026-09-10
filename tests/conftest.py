import os
import pathlib
import tempfile

# Must be set before anything under advisor.api is imported.
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="advisor-test-"))
os.environ["API_SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-xx"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["ALLOW_REGISTRATION"] = "true"

from cryptography.fernet import Fernet  # noqa: E402

os.environ["SECRETS_ENC_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from advisor.api import models_db  # noqa: F401  (register mappers)
    from advisor.api.db import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    from advisor.api.main import app

    with TestClient(app) as c:
        yield c
