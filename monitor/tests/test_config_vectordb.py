
import pytest
from pydantic import ValidationError

from monitor.config import VectorDBConfig, VectorDBType


def test_vectordb_connection_string_validation_passes():
    cfg = VectorDBConfig(db_type=VectorDBType.QDRANT, connection_string="http://localhost:6333")
    assert cfg.connection_string.startswith("http://")


def test_vectordb_connection_string_validation_fails_on_memory_scheme():
    with pytest.raises(ValidationError):
        VectorDBConfig(db_type=VectorDBType.QDRANT, connection_string="memory://")

