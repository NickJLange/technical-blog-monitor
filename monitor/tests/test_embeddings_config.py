from monitor.config import EmbeddingConfig
from monitor.embeddings import DummyEmbeddingClient


def test_embedding_image_dimensions_default():
    cfg = EmbeddingConfig(text_model_type='custom')
    assert cfg.image_embedding_dimensions == 512


def test_dummy_embedding_uses_configured_dimensions():
    cfg = EmbeddingConfig(text_model_type='custom', embedding_dimensions=1536, image_embedding_dimensions=256)
    client = DummyEmbeddingClient(cfg)
    # Access internals to assert chosen dims
    assert client.text_dim == 1536
    assert client.image_dim == 256

