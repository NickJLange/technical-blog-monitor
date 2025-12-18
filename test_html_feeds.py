import asyncio
import httpx
from monitor.config import FeedConfig
from monitor.feeds.html_fallback import HTMLFallbackFeedProcessor

test_feeds = {
    "GitHub Blog": "https://github.blog/",
    "Cloudflare Blog": "https://blog.cloudflare.com/",
    "MongoDB Blog": "https://www.mongodb.com/blog/",
    "Hugging Face": "https://huggingface.co/blog",
    "Kubernetes": "https://kubernetes.io/blog/",
    "Canva Engineering": "https://www.canva.dev/blog/engineering/",
    "Apache Kafka": "https://kafka.apache.org/blog",
    "Anthropic": "https://www.anthropic.com/news",
}

async def test_feed(name, url):
    try:
        config = FeedConfig(name=name, url=url)
        processor = HTMLFallbackFeedProcessor(config)
        
        async with httpx.AsyncClient(timeout=15) as client:
            content = await processor.fetch_feed(client)
            entries = await processor.parse_feed(content)
            posts = await processor.extract_posts(entries)
            print(f"✓ {name:30s} - {len(posts):2d} articles")
            return len(posts) > 0
    except Exception as e:
        print(f"✗ {name:30s} - {str(e)[:60]}")
        return False

async def main():
    print("\nTesting HTML fallback feeds...\n")
    results = {}
    for name, url in test_feeds.items():
        result = await test_feed(name, url)
        results[name] = result
    
    working = sum(1 for r in results.values() if r)
    print(f"\n\nSummary: {working}/{len(results)} working")

asyncio.run(main())
