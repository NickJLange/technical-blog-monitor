"""End-to-end performance test of the unified PostgreSQL+cache architecture."""
import asyncio
import time
from datetime import datetime
from monitor.config import load_settings, CacheBackend, VectorDBType
from monitor.cache import get_cache_client
from monitor.db.postgres_pool import get_pool, close_pool

async def main():
    start_time = time.time()
    
    print("=" * 70)
    print("E2E Performance Test: Unified PostgreSQL+Cache Architecture")
    print("=" * 70)
    print(f"Start time: {datetime.now().isoformat()}\n")
    
    # Load settings
    settings = load_settings()
    print(f"Configuration loaded:")
    print(f"  Cache backend: {settings.cache.backend}")
    print(f"  Vector DB type: {settings.vector_db.db_type}")
    print(f"  Feeds: {[f.name for f in settings.feeds]}\n")
    
    # Test cache performance
    print("Testing Cache Performance...")
    cache_start = time.time()
    cache_client = await get_cache_client(settings.cache, settings.vector_db)
    cache_init_time = time.time() - cache_start
    print(f"  Cache initialization: {cache_init_time:.3f}s")
    
    # Write test data
    write_start = time.time()
    for i in range(100):
        await cache_client.set(f"test:key:{i}", {"data": f"value_{i}", "index": i})
    write_time = time.time() - write_start
    print(f"  Write 100 entries: {write_time:.3f}s ({100/write_time:.1f} ops/sec)")
    
    # Read test data
    read_start = time.time()
    for i in range(100):
        val = await cache_client.get(f"test:key:{i}")
        assert val is not None, f"Missing key test:key:{i}"
    read_time = time.time() - read_start
    print(f"  Read 100 entries: {read_time:.3f}s ({100/read_time:.1f} ops/sec)")
    
    # Cleanup
    await cache_client.clear()
    await cache_client.close()
    
    print("\n" + "=" * 70)
    print("Memory Usage (peak):")
    import psutil
    process = psutil.Process()
    mem_info = process.memory_info()
    print(f"  RSS: {mem_info.rss / 1024 / 1024:.1f} MB")
    print(f"  VMS: {mem_info.vms / 1024 / 1024:.1f} MB")
    
    total_time = time.time() - start_time
    print(f"\nTotal test time: {total_time:.2f}s")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
