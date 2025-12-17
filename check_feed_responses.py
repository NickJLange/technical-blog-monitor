import asyncio
import httpx
from monitor.feeds.base import fetch_with_retry, DEFAULT_HEADERS, DEFAULT_USER_AGENT

feeds = {
    "Netflix Tech Blog": "https://netflixtechblog.com/feed",
    "Lyft Engineering": "https://eng.lyft.com/feed",
    "Airbnb Engineering": "https://medium.com/airbnb-engineering",
    "Slack Engineering": "https://slack.engineering/feed/",
    "Spotify Engineering": "https://engineering.atspotify.com/feed",
    "Stripe Engineering": "https://stripe.com/blog/feed.rss",
    "HashiCorp Blog": "https://www.hashicorp.com/blog/feed.xml",
    "Redis Blog": "https://redis.io/blog/feed/",
}

async def check_feed(name, url):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                headers={**DEFAULT_HEADERS, "User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True
            )
            ct = response.headers.get("content-type", "")
            is_rss = "xml" in ct or "atom" in ct or "rss" in ct
            return f"✓ {name:30s} - {response.status_code} {ct[:40]:40s} {'[RSS]' if is_rss else '[HTML]'}"
    except Exception as e:
        return f"✗ {name:30s} - {str(e)[:50]}"

async def main():
    for name, url in feeds.items():
        result = await check_feed(name, url)
        print(result)

asyncio.run(main())
