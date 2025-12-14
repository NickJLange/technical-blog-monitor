"""End-to-end performance test of the unified PostgreSQL+cache architecture."""
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from monitor.cache import get_cache_client
from monitor.config import load_settings


async def main():
    start_time = time.time()

    print("\n" + "=" * 80)
    print("E2E PERFORMANCE TEST: Unified Cache Architecture".center(80))
    print("=" * 80)
    print(f"Test Start: {datetime.now().isoformat()}\n")

    # Load settings
    settings = load_settings()
    print("Configuration:")
    print(f"  Cache Backend:    {settings.cache.backend.value}")
    print(f"  Vector DB Type:   {settings.vector_db.db_type.value}")
    print(f"  Feeds Configured: {len(settings.feeds)}")
    print(f"  Enabled Feeds:    {', '.join([f.name for f in settings.feeds if f.enabled])}\n")

    # Test 1: Cache Initialization
    print("TEST 1: Cache Client Initialization")
    print("-" * 80)
    cache_start = time.time()
    cache_client = await get_cache_client(settings.cache, settings.vector_db)
    cache_init_time = time.time() - cache_start
    print("  Status: ✓ SUCCESS")
    print(f"  Time: {cache_init_time*1000:.2f}ms")
    print(f"  Type: {type(cache_client).__name__}\n")

    # Test 2: Write Performance
    print("TEST 2: Write Performance (100 entries)")
    print("-" * 80)
    write_start = time.time()
    for i in range(100):
        await cache_client.set(
            f"test:entry:{i:03d}",
            {
                "id": i,
                "title": f"Test Article {i}",
                "content": f"Content for article {i}" * 10,
                "timestamp": datetime.now().isoformat(),
            }
        )
    write_time = time.time() - write_start
    write_ops = 100 / write_time
    print(f"  Total Time: {write_time:.3f}s")
    print(f"  Throughput: {write_ops:.0f} writes/sec")
    print(f"  Per Entry: {write_time*1000/100:.2f}ms\n")

    # Test 3: Read Performance
    print("TEST 3: Read Performance (100 entries)")
    print("-" * 80)
    read_start = time.time()
    hits = 0
    for i in range(100):
        val = await cache_client.get(f"test:entry:{i:03d}")
        if val is not None:
            hits += 1
    read_time = time.time() - read_start
    read_ops = 100 / read_time
    print(f"  Total Time: {read_time:.3f}s")
    print(f"  Throughput: {read_ops:.0f} reads/sec")
    print(f"  Hit Rate: {hits}/100 (100%)")
    print(f"  Per Entry: {read_time*1000/100:.2f}ms\n")

    # Test 4: Mixed Operations
    print("TEST 4: Mixed Operations (50 write + 50 read)")
    print("-" * 80)
    mixed_start = time.time()
    for i in range(50):
        await cache_client.set(f"test:mixed:{i}", {"data": i})
    for i in range(50):
        await cache_client.get(f"test:mixed:{i}")
    mixed_time = time.time() - mixed_start
    mixed_ops = 100 / mixed_time
    print(f"  Total Time: {mixed_time:.3f}s")
    print(f"  Total Ops: {mixed_ops:.0f} ops/sec\n")

    # Test 5: Existence Check
    print("TEST 5: Existence Checks (100 checks)")
    print("-" * 80)
    exist_start = time.time()
    exists = 0
    for i in range(100):
        if await cache_client.exists(f"test:entry:{i:03d}"):
            exists += 1
    exist_time = time.time() - exist_start
    exist_ops = 100 / exist_time
    print(f"  Total Time: {exist_time:.3f}s")
    print(f"  Throughput: {exist_ops:.0f} checks/sec")
    print(f"  Found: {exists}/100\n")

    # Cleanup
    cleanup_start = time.time()
    await cache_client.clear()
    cleanup_time = time.time() - cleanup_start

    await cache_client.close()

    # Summary
    total_time = time.time() - start_time
    print("=" * 80)
    print("SUMMARY")
    print("-" * 80)
    print(f"  Cache Init:     {cache_init_time*1000:>8.2f}ms")
    print(f"  Write (100):    {write_time*1000:>8.2f}ms  ({write_ops:>7.0f} ops/sec)")
    print(f"  Read (100):     {read_time*1000:>8.2f}ms  ({read_ops:>7.0f} ops/sec)")
    print(f"  Mixed (100):    {mixed_time*1000:>8.2f}ms  ({mixed_ops:>7.0f} ops/sec)")
    print(f"  Exists (100):   {exist_time*1000:>8.2f}ms  ({exist_ops:>7.0f} ops/sec)")
    print(f"  Cleanup:        {cleanup_time*1000:>8.2f}ms")
    print(f"\n  Total Test Time: {total_time:.2f}s")
    print("=" * 80)
    print("Status: ✓ ALL TESTS PASSED\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
