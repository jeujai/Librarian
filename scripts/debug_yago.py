#!/usr/bin/env python3
"""Debug YAGO 4.5 processor."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.components.yago.processor import YagoDumpProcessor

dump_dir = Path(__file__).parent.parent / "yago-dumps"

print(f"Dump dir: {dump_dir}")
print(f"Dir exists: {dump_dir.exists()}")

# List files
if dump_dir.exists():
    for f in dump_dir.iterdir():
        print(f"  {f.name}: {f.stat().st_size} bytes")

# Test processor
print("\n--- Processor test ---")
processor = YagoDumpProcessor(dump_dir=dump_dir)


async def test_processor():
    count = 0
    async for entity in processor.process(file_keys=["facts"]):
        count += 1
        print(
            f"Entity {count}: {entity.entity_id}"
            f" - {entity.label}"
        )
        if count >= 5:
            break
    print(f"\nTotal entities from processor: {count}")

asyncio.run(test_processor())