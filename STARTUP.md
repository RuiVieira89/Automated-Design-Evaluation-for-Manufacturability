# Project Startup Scripts

This directory contains bash scripts to easily start and stop the entire CAD Design Evaluation system.

## Quick Start

### Start everything:
```bash
bash start_project.sh
```

### Start with Celery workers:
```bash
bash start_project.sh --with-celery
```

### Stop everything:
```bash
bash stop_project.sh
```

## What start_project.sh Does

The startup script performs the following steps in order:

1. **Verifies conda installation** - Ensures conda is available
2. **Activates conda environment** - Activates the `auto_eval_manuf` environment
3. **Sets environment variables** - Configures PYTHONPATH, Redis, FastAPI, and Celery settings
4. **Checks Redis** - Verifies Redis is installed, starts it if needed
5. **Starts FastAPI** - Launches the REST API server on `http://localhost:8000`
6. **Optionally starts Celery** - Starts worker processes if requested
7. **Displays status** - Shows running services and quick start commands

### Default Configuration

The script uses these defaults (can be overridden with environment variables):

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB_BROKER=1
REDIS_DB_BACKEND=2
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
CONDA_ENV=auto_eval_manuf
```

### Custom Configuration

Override settings before running:

```bash
# Use a different Redis host
export REDIS_HOST=192.168.1.100
bash start_project.sh

# Use a different FastAPI port
export FASTAPI_PORT=9000
bash start_project.sh

# Start with Celery from the beginning
bash start_project.sh --with-celery
```

## What stop_project.sh Does

The shutdown script:

1. **Stops FastAPI server** - Terminates the API service
2. **Stops Celery worker** - Terminates any running Celery processes
3. **Stops Redis** - Gracefully shuts down Redis server
4. **Cleans up logs** - Removes temporary log files

## Logs and Debugging

After startup, logs are available in the project root:

```bash
# Watch FastAPI logs in real-time
tail -f fastapi.log

# Watch Celery logs
tail -f celery.log

# Watch Redis logs
tail -f redis.log
```

## Troubleshooting

### Redis connection refused
```bash
# Check if Redis is running
redis-cli ping

# Start Redis manually
redis-server

# Or check Redis logs
tail -f redis.log
```

### FastAPI port already in use
```bash
# Find what's using port 8000
lsof -i :8000

# Use a different port
export FASTAPI_PORT=9000
bash start_project.sh
```

### Conda environment not found
```bash
# List available environments
conda env list

# Update the CONDA_ENV variable or create the environment
conda create -n auto_eval_manuf python=3.13
```

### Permission denied
```bash
# Make scripts executable
chmod +x start_project.sh stop_project.sh

# Or run with bash explicitly
bash start_project.sh
```

## Manual Service Management

If you prefer to start services individually:

```bash
# Start Redis (in background)
redis-server --daemonize yes

# Start FastAPI (in new terminal)
cd synchronous_request_plane_FastAPI
python fastapi_app.py

# Start Celery (in new terminal)
cd synchronous_request_plane_FastAPI
celery -A celery_tasks worker --loglevel=info
```

## Testing the System

Once everything is running:

```bash
# Check health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs

# Submit a test job
curl -X POST http://localhost:8000/analyze \
  -F "file=@data/cube.off" \
  -F "process_type=single"
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB_BROKER` | `1` | Redis database for Celery broker |
| `REDIS_DB_BACKEND` | `2` | Redis database for Celery results |
| `FASTAPI_HOST` | `0.0.0.0` | FastAPI server host |
| `FASTAPI_PORT` | `8000` | FastAPI server port |
| `PYTHONPATH` | Auto-set | Python module search path |
| `CELERY_BROKER_URL` | Auto-set | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Auto-set | Celery result backend URL |

## Notes

- Scripts must be run from the project root directory
- The `auto_eval_manuf` conda environment must exist
- Redis must be installed (installable via `conda install -c conda-forge redis`)
- Scripts will display colored output for easy reading
- Process IDs are shown for manual management if needed
- All services run in the background except when explicitly daemonized
