import asyncio
import httpx
from monitor.config import FeedConfig
from monitor.feeds.rss import RSSFeedProcessor

test_feeds = {
    "Lyft Engineering": "https://eng.lyft.com/feed",
    "Spotify Engineering": "https://engineering.atspotify.com/feed",
}

async def debug_feed(name, url):
    try:
        config = FeedConfig(name=name, url=url)
        processor = RSSFeedProcessor(config)
        
        async with httpx.AsyncClient(timeout=15) as client:
            content = await processor.fetch_feed(client)
            print(f"\n{name}:")
            print(f"  Content length: {len(content)} bytes")
            print(f"  Content type: {content[:100]}")
            
            entries = await processor.parse_feed(content)
            print(f"  Entries parsed: {len(entries)}")
            if entries:
                print(f"  First entry: {entries[0]}")
            
            posts = await processor.extract_posts(entries)
            print(f"  Posts extracted: {len(posts)}")
            
    except Exception as e:
        print(f"\n{name}: ERROR - {str(e)[:100]}")

async def main():
    for name, url in test_feeds.items():
        await debug_feed(name, url)

asyncio.run(main())
