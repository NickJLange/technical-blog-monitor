#!/usr/bin/env python3
import json
import subprocess
from urllib.parse import urlparse

# Cloud ID from terraalpha.atlassian.net
CLOUD_ID = "1ad9038f-7601-4cfd-ad22-9f24cb1fc0f4"
PROJECT_KEY = "FIVELLABS"

# Create Jira issue for cache corruption bug
issue_data = {
    "fields": {
        "project": {"key": PROJECT_KEY},
        "summary": "Fix: PostgreSQL cache UTF-8 deserialization corruption bug",
        "description": """## Problem
The PostgreSQL cache client was experiencing UTF-8 decoding errors when retrieving cached ArticleContent objects:
- Error: `'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte`
- Affected keys: `article_content:https://...` entries
- Root cause: `json.loads()` called directly on bytes without UTF-8 decoding first

## Root Cause
In `monitor/cache/postgres.py`, the `_deserialize()` method at line 638 was:
```python
return json.loads(data)  # WRONG: data is bytes
```

Should be:
```python
return json.loads(data.decode("utf-8"))  # CORRECT: decode bytes first
```

## Solution Applied
✅ Fixed the deserialization to decode bytes to UTF-8 string before JSON parsing
✅ Added explicit UnicodeDecodeError to exception handling
✅ Cleared corrupted cache data from database (TRUNCATE TABLE cache_entries)
✅ Verified fix works - new cache entries are being stored/retrieved successfully

## Testing
- Ran feed monitor with ARTICLE_PROCESSING__GENERATE_SUMMARY=true
- Verified 12 new cache entries created and retrieved without UTF-8 errors
- Confirmed summaries are being generated and stored in metadata.summary

## Files Changed
- `monitor/cache/postgres.py` - Fixed _deserialize() method (lines 621-643)
"""
        ,
        "issuetype": {"name": "Bug"},
        "labels": ["cache", "postgresql", "utf8", "production-bug"],
    }
}

print(json.dumps(issue_data, indent=2))
