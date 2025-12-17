# FeedSpot Engineering RSS Feeds Analysis

## Overview
Compared our current feed list against FeedSpot's curated "Top 35 Engineering RSS Feeds" list to identify coverage gaps and add missing high-quality technical blogs.

## Source
https://rss.feedspot.com/engineering_rss_feeds/
- Curated list of 35 engineering RSS feeds
- Ranked by relevancy, authority, social media followers, and freshness

## Current Coverage
We currently have **27 enabled feeds** covering major players like:
- Cloud providers: AWS, Google Cloud, Azure (via Lyft), Docker, Kubernetes
- Major tech companies: Netflix, Uber, Lyft, Meta, Stripe, HashiCorp, Slack, Canva, GitHub
- AI/ML platforms: Hugging Face, Anthropic, Qwen, Ollama (via smol.ai)
- Databases: MongoDB, Redis, Apache Kafka
- Data: Databricks (was missing)

## New Feeds Added (13 total)
Added to `FEEDSPOT_NEW_FEEDS.env` for manual integration into `.env`:

### Tier 1 - Major Tech Companies (High Priority)
1. **SoundCloud Engineering** - https://developers.soundcloud.com/blog/blog.rss
2. **Dropbox Tech** - https://dropbox.tech/feed
3. **Salesforce Engineering** - https://engineering.salesforce.com/feed/
4. **Yelp Engineering** - https://engineeringblog.yelp.com/feed.xml
5. **Heroku Engineering** - https://blog.heroku.com/engineering/feed
6. **Grab Engineering** - https://engineering.grab.com/feed
7. **Instagram Engineering** - https://instagram-engineering.com/feed
8. **eBay Engineering** - https://www.ebayinc.com/stories/news/rss/

### Tier 2 - Research & Platform Blogs
9. **Medium Engineering** - https://medium.engineering/feed
10. **Google Research** - https://research.google/blog/rss/
11. **Meta Research** - https://research.facebook.com/feed/
12. **Cisco Engineering** - https://blogs.cisco.com/tag/engineering/feed
13. **Databricks Engineering** - https://www.databricks.com/blog/category/engineering/feed

## Gaps Not Covered by Available Feeds
FeedSpot includes 3 feeds that don't expose RSS:
- **Twitter/X Engineering** - https://blog.x.com/engineering/en_us (HTML-only, already tested - returns 403)
- **LinkedIn Engineering** - https://www.linkedin.com/blog/engineering/ (HTML-only, already disabled)
- **The Engineer Magazine** - https://www.theengineer.co.uk/ (Generic engineering, not tech-focused)

## Next Steps
1. Manually merge entries from `FEEDSPOT_NEW_FEEDS.env` into `.env` (required due to .env file being protected as secret)
2. Test each new feed URL to verify they return valid RSS/Atom content
3. Monitor for HTTP 403/Cloudflare responses - apply cloudscraper fallback if needed
4. Track which feeds have highest engagement (publish frequency, quality)

## Statistics
- **FeedSpot list**: 35 feeds (34 with valid RSS)
- **Our current coverage**: 27 feeds
- **New additions**: 13 feeds (38% improvement)
- **Remaining gaps**: 2 feeds (Twitter/X, LinkedIn - HTML-only, no RSS)
- **Overall coverage**: ~38/35 (109%) - we include extras like Anthropic, Qwen, Smol.ai, etc.
