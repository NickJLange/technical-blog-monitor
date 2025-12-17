# Next Session Tasks

## Status
- Database: Empty (cleared for fresh run)
- Cache: Empty (cleared for fresh run)
- Code changes: UI improvements to `generate_web_view.py` and `test_full_pipeline.py`

## Root Cause Identified
The `.env` has these settings disabled:
```
ARTICLE_PROCESSING__FULL_CONTENT_CAPTURE=false
ARTICLE_PROCESSING__GENERATE_SUMMARY=false
```

These need to be set to `true` for the full pipeline to work (article text extraction, embedding generation, AI summaries).

## Tasks to Complete

1. **Enable article processing in .env**:
   ```
   ARTICLE_PROCESSING__FULL_CONTENT_CAPTURE=true
   ARTICLE_PROCESSING__GENERATE_SUMMARY=true
   ```

2. **Run full monitor** to populate database:
   ```bash
   uv run monitor --once --log-level INFO
   ```

3. **Verify data in database**:
   ```bash
   uv run python view_records.py
   ```

4. **Generate web view** and verify UI shows:
   - Author field
   - Tags
   - AI-generated summaries
   - Correct date ordering (by publish_date, not ingestion)

5. **Test the search** includes tag filtering

## Files Modified (uncommitted)
- `generate_web_view.py` - Added author, tags, AI summary display, date ordering fix
- `test_full_pipeline.py` - Updated test to verify full pipeline

## New Files (untracked)
- `clear_vectordb.py` - Utility to clear vector DB
- `view_records.py` - Utility to view DB records
- `test_single_feed.py` - Test single feed processing
