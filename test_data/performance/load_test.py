
#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import json
from concurrent.futures import ThreadPoolExecutor

class LoadTester:
    def __init__(self, base_url, concurrent_users=10):
        self.base_url = base_url
        self.concurrent_users = concurrent_users
        self.results = []
    
    async def simulate_user_session(self, user_id):
        async with aiohttp.ClientSession() as session:
            # Upload document
            start_time = time.time()
            # ... upload logic ...
            upload_time = time.time() - start_time
            
            # Chat queries
            for i in range(5):
                start_time = time.time()
                # ... chat logic ...
                chat_time = time.time() - start_time
                
                self.results.append({
                    'user_id': user_id,
                    'operation': 'chat',
                    'response_time': chat_time,
                    'timestamp': time.time()
                })
    
    async def run_load_test(self, duration_minutes=10):
        tasks = []
        for user_id in range(self.concurrent_users):
            task = asyncio.create_task(self.simulate_user_session(user_id))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        return self.analyze_results()
    
    def analyze_results(self):
        # Calculate metrics
        response_times = [r['response_time'] for r in self.results]
        avg_response_time = sum(response_times) / len(response_times)
        p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
        
        return {
            'total_requests': len(self.results),
            'avg_response_time': avg_response_time,
            'p95_response_time': p95_response_time,
            'throughput_rps': len(self.results) / (max(r['timestamp'] for r in self.results) - min(r['timestamp'] for r in self.results))
        }

if __name__ == "__main__":
    tester = LoadTester("http://localhost:8000", concurrent_users=10)
    results = asyncio.run(tester.run_load_test(duration_minutes=5))
    print(json.dumps(results, indent=2))
