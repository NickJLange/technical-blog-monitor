from pydantic import BaseModel

# Ensure canonical models are re-exported and not redefined here
from monitor.models import EmbeddingRecord, BlogPost, ArticleContent, CacheEntry


def test_models_exports_refer_to_canonical_types():
    # Sanity: they should be Pydantic models and have expected attributes
    assert issubclass(EmbeddingRecord, BaseModel)
    fields = getattr(EmbeddingRecord, "model_fields", {})
    assert "url" in fields and "title" in fields
    assert ("text_embedding" in fields) or ("image_embedding" in fields)
    assert issubclass(BlogPost, BaseModel)
    assert issubclass(ArticleContent, BaseModel)
    assert issubclass(CacheEntry, BaseModel)

