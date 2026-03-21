This layer is best understood as two independent planes stacked on top of each other — a synchronous request plane (FastAPI) and an asynchronous execution plane (Celery + Prefect/Airflow) — with Redis as the shared nervous system between them. I'll show the overall topology first, then zoom into the job lifecycle.

see orchestration_layer6_overview.svg

The two-plane structure is the key decision. Now here's the job lifecycle — what actually happens between a POST /analyse arriving and a result coming back:

see orchestration_layer6_job_lifecycle.svg

The job lifecycle diagram shows the state machine that every job moves through, and where each tool owns each transition.
A few structural decisions worth locking in:
FastAPI never blocks on pipeline execution. Every /analyse call returns a job_id immediately — the response is 202 Accepted, not 200 OK. Clients poll GET /job/{id} against Redis to check state. This keeps the sync plane thin and fast regardless of how long the geometry takes to process, and it makes the FreeCAD plugin, web UI, and CI/CD client all structurally identical — they all poll.
Celery and Prefect/Airflow are complementary, not alternatives. Celery owns individual task execution — one analyse_part task per component, with fan-out via chord for assemblies. Prefect (or Airflow) owns the flow DAG above it — it knows that a 200-part assembly needs N tasks, in what dependency order, with what caching and retry policies. Prefect submits tasks to Celery; it doesn't execute geometry itself. The distinction is: Celery is a task runner, Prefect is a workflow coordinator.
The chord pattern is the load-bearing structure for assemblies. A chord(analyse_part.s(component) for component in assembly) | aggregate.s() fires all component analyses in parallel, then calls the aggregate callback only when all succeed. This is where most of the wall-clock time for large assemblies gets recovered. The chord callback writes the merged result back to Redis under the parent job ID, so the polling client sees a single SUCCESS state with a unified report.
Redis serves two distinct roles — keep them separate in config. As a Celery broker, Redis holds task messages (short-lived, high-throughput). As a result backend, it holds job state and output payloads (longer-lived, needs TTL management). Use separate Redis databases (or a separate instance) for the two roles, and set an explicit TTL on result keys — otherwise completed job results accumulate indefinitely on large assembly batch runs.
Prefect vs Airflow comes down to your deployment context. Prefect's Python-native flow definitions fit better with a codebase that's already all Python; Airflow's DAG model is more familiar in data engineering contexts and has broader enterprise integrations. If this is a greenfield build, Prefect 2.x is the lighter-weight choice.

## Setup and Installation

### Prerequisites
- Python 3.13+
- Redis server
- (Optional) Prefect server for advanced workflow orchestration

### Dependencies
```bash
pip install fastapi uvicorn celery redis prefect pyvista
```

### Configuration
The orchestration layer uses environment variables for configuration:

```bash
# Redis settings
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB_BROKER=1
export REDIS_DB_BACKEND=2

# FastAPI settings
export FASTAPI_HOST=0.0.0.0
export FASTAPI_PORT=8000

# Celery settings
export CELERY_BROKER_URL=redis://localhost:6379/1
export CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Prefect settings (optional)
export PREFECT_API_URL=http://localhost:4200/api
```

## Usage

### 1. Start Redis Server
```bash
redis-server
```

### 2. Start FastAPI Server
```bash
cd synchronous_request_plane_FastAPI
PYTHONPATH=/path/to/project/root python fastapi_app.py
```

The API will be available at `http://localhost:8000`

### 3. Start Celery Workers
```bash
cd synchronous_request_plane_FastAPI
PYTHONPATH=/path/to/project/root celery -A celery_tasks worker --loglevel=info
```

### 4. (Optional) Start Prefect Server
```bash
prefect server start
```

## API Usage

### Submit Analysis Job
```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "file=@part.stl" \
  -F "process_type=single"
```

Response:
```json
{
  "job_id": "uuid-string",
  "status": "accepted",
  "message": "Analysis job submitted successfully",
  "poll_url": "/job/uuid-string"
}
```

### Check Job Status
```bash
curl "http://localhost:8000/job/{job_id}"
```

Response:
```json
{
  "job_id": "uuid-string",
  "status": "SUCCESS",
  "created_at": "2024-01-01T00:00:00",
  "completed_at": "2024-01-01T00:01:30",
  "result": {
    "rule_results": [...],
    "ml_assessment": {...},
    "visualizations": [...]
  }
}
```

### Cancel Job
```bash
curl -X DELETE "http://localhost:8000/job/{job_id}"
```

## Prefect Flow Usage

### Run Single Part Analysis
```python
from synchronous_request_plane_FastAPI.prefect_flows import single_part_analysis_flow

result = single_part_analysis_flow(
    job_id="my_job",
    file_path="/path/to/part.stl",
    rules_config={"wall_thickness": {"min_thickness": 2.0}}
)
```

### Run Assembly Analysis
```python
from synchronous_request_plane_FastAPI.prefect_flows import assembly_analysis_flow

result = assembly_analysis_flow(
    job_id="assembly_job",
    assembly_file="/path/to/assembly.stl"
)
```

### Run Batch Analysis
```python
from synchronous_request_plane_FastAPI.prefect_flows import batch_analysis_flow

result = batch_analysis_flow(
    job_ids=["job1", "job2", "job3"],
    file_paths=["part1.stl", "part2.stl", "part3.stl"],
    process_types=["single", "single", "assembly"]
)
```

## Testing

Run the orchestration tests:

```bash
cd /path/to/project/root
python -m pytest tests/test_orchestration_fastapi.py -v
python -m pytest tests/test_orchestration_celery.py -v
python -m pytest tests/test_orchestration_prefect.py -v
```

## Architecture Notes

### Synchronous Plane (FastAPI)
- Handles HTTP requests and responses
- Validates input and returns job IDs immediately
- No blocking operations - all work is asynchronous

### Asynchronous Plane (Celery)
- Executes the actual analysis pipeline (L1-L5)
- Supports progress tracking and cancellation
- Scales horizontally with multiple workers

### Workflow Orchestration (Prefect)
- Manages complex workflows like assembly analysis
- Provides scheduling and dependency management
- Offers UI for monitoring and debugging

### Redis Usage
- **Database 1**: Celery task broker (short-lived messages)
- **Database 2**: Celery result backend (job state and results)
- Results have 1-hour TTL to prevent accumulation

## Deployment

### Docker Compose Example
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  fastapi:
    build: .
    environment:
      - REDIS_HOST=redis
      - FASTAPI_HOST=0.0.0.0
    ports:
      - "8000:8000"
    depends_on:
      - redis

  celery-worker:
    build: .
    command: celery -A synchronous_request_plane_FastAPI.celery_tasks worker --loglevel=info
    environment:
      - REDIS_HOST=redis
    depends_on:
      - redis
```

### Production Considerations
- Use separate Redis instances for broker and backend
- Configure Celery result expiration
- Set up monitoring (Flower for Celery, Prefect UI)
- Implement proper logging and error handling
- Consider using a message queue like RabbitMQ for high throughput