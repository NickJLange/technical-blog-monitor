import asyncio
import httpx
from monitor.feeds.base import fetch_with_retry, DEFAULT_HEADERS, DEFAULT_USER_AGENT

feeds = {
    "Uber Engineering": "https://www.uber.com/en-US/blog/engineering/rss/",
    "Cloudflare Blog": "https://blog.cloudflare.com/",
    "LinkedIn Engineering": "https://www.linkedin.com/blog/engineering/feed",
    "Anthropic": "https://www.anthropic.com/news",
    "Hugging Face": "https://huggingface.co/blog",
    "GitHub Blog": "https://github.blog/",
    "GitLab Blog": "https://about.gitlab.com/blog/",
    "Kubernetes": "https://kubernetes.io/blog/",
    "MongoDB Blog": "https://www.mongodb.com/blog/",
    "Canva Engineering": "https://www.canva.dev/blog/engineering/",
    "Apache Kafka": "https://kafka.apache.org/blog",
    "Qwen LLM": "https://qwenlm.github.io/blog/",
    "DeepMind": "https://deepmind.google/",
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
            return (name, response.status_code, ct, is_rss)
    except Exception as e:
        return (name, None, str(e)[:50], None)

async def main():
    results = []
    for name, url in feeds.items():
        result = await check_feed(name, url)
        results.append(result)
    
    # Sort by: RSS feeds first, then 200 responses, then errors
    results.sort(key=lambda x: (not x[3], x[1] != 200 if x[1] else True, x[0]))
    
    for name, status, ct, is_rss in results:
        if status:
            marker = "✓" if status == 200 else "~"
            rss_marker = "[RSS]" if is_rss else "[HTML]"
            print(f"{marker} {name:30s} - {status} {ct[:40]:40s} {rss_marker}")
        else:
            print(f"✗ {name:30s} - {ct}")

asyncio.run(main())
