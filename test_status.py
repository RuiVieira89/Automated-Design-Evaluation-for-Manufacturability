#!/usr/bin/env python
"""
Quick test script to check if Celery tasks are completing and returning SUCCESS status.
"""
import json
import redis
import time
from datetime import datetime
from celery import Celery
import os

# Setup Redis and Celery
REDIS_URL = "redis://localhost:6379/0"
CELERY_BROKER_URL = "redis://localhost:6379/1"
CELERY_RESULT_BACKEND = "redis://localhost:6379/2"

redis_client = redis.from_url(REDIS_URL)
celery_app = Celery(
    'orchestration',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

def main():
    print("Checking for completed Celery tasks in Redis...\n")
    
    # Scan Redis for job keys
    cursor = 0
    job_count = 0
    
    while True:
        cursor, keys = redis_client.scan(cursor, match="job:*", count=10)
        
        for key in keys:
            job_count += 1
            job_data_str = redis_client.get(key)
            if job_data_str:
                job_data = json.loads(job_data_str.decode())
                job_id = job_data.get('job_id', 'unknown')
                status = job_data.get('status', 'unknown')
                celery_task_id = job_data.get('celery_task_id', None)
                
                print(f"Job: {job_id}")
                print(f"  Status in Redis: {status}")
                print(f"  Celery Task ID: {celery_task_id}")
                
                if celery_task_id:
                    task_result = celery_app.AsyncResult(celery_task_id)
                    print(f"  Celery Task State: {task_result.state}")
                    print(f"  Task Ready: {task_result.ready()}")
                    
                    if task_result.ready():
                        if task_result.state == "SUCCESS":
                            print(f"  ✓ Task completed successfully")
                            if task_result.result:
                                result_keys = list(task_result.result.keys()) if isinstance(task_result.result, dict) else ["<not a dict>"]
                                print(f"  Result keys: {result_keys}")
                        elif task_result.state == "FAILURE":
                            print(f"  ✗ Task failed: {task_result.info}")
                    else:
                        print(f"  ⏳ Task still processing")
                
                print()
        
        if cursor == 0:
            break
    
    print(f"Total jobs found: {job_count}")
    
    if job_count == 0:
        print("\nNo jobs found in Redis. Run the demo first or check that jobs are being stored.")
        
        # Check if Redis is connected
        try:
            redis_client.ping()
            print("✓ Redis is connected")
        except Exception as e:
            print(f"✗ Redis connection failed: {e}")

if __name__ == "__main__":
    main()
