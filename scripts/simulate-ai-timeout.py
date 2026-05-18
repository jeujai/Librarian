#!/usr/bin/env python3
"""
Simulate an AI provider timeout by running a blackhole HTTP proxy.
Accepts connections from the chat backend but never responds,
triggering the full cascade: timeout -> retry -> circuit breaker -> offline warnings.

Usage:
  1. python scripts/simulate-ai-timeout.py --port 9999
  2. Set DEEPSEEK_BASE_URL=http://localhost:9999 in your .env
  3. Restart the app
  4. Send 5+ messages in chat — watch the timeout / circuit breaker / offline warnings
  5. Ctrl+C this script to restore normal operation (and remove the env override)
"""
import argparse
import asyncio
import signal
import sys

shutdown = False


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Accept connection, read headers, then hang forever."""
    try:
        # Read the HTTP request so the client thinks it connected successfully
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        print(f"  [hang] connection from {writer.get_extra_info('peername')} — holding open indefinitely")
        # Never respond — simulates a hung upstream
        while not shutdown:
            await asyncio.sleep(1)
    except asyncio.TimeoutError:
        print("  [hang] client didn't send complete headers, holding anyway")
        while not shutdown:
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        writer.close()


async def main(port: int, duration: float | None):
    global shutdown

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    print(f"Blackhole proxy listening on http://127.0.0.1:{port}")
    print("All connections will hang until this script exits.")
    print(f"Set DEEPSEEK_BASE_URL=http://127.0.0.1:{port} and restart the app.")
    print()

    if duration:
        print(f"Will auto-shutdown after {duration}s")
        asyncio.get_event_loop().call_later(duration, lambda: setattr(sys.modules[__name__], "shutdown", True))

    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass

    print("\nShutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate AI provider timeout")
    parser.add_argument("--port", type=int, default=9999, help="Port to listen on (default: 9999)")
    parser.add_argument("--duration", type=float, default=None, help="Auto-shutdown after N seconds")
    args = parser.parse_args()

    def _sig_handler(sig, frame):
        global shutdown
        shutdown = True
        print("\nReceived signal, shutting down...")

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    asyncio.run(main(args.port, args.duration))
