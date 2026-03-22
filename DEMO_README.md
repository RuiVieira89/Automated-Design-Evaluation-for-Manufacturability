# CAD Design Evaluation Demo

This demo script (`demo.sh`) provides a complete end-to-end demonstration of the Automated Design Evaluation for Manufacturability system.

## What it does

1. **Starts all services**: Redis, FastAPI server, and Celery workers
2. **Submits analysis**: Automatically submits the `FlandersMake_part-Merger.stl` file for manufacturability analysis
3. **Polls for results**: Monitors the analysis job until completion
4. **Shows 3D visualization**: Launches a web UI or creates a 3D screenshot of the analyzed part

## Quick Start

```bash
# Make sure you're in the project root directory
cd /path/to/Automated-Design-Evaluation-for-Manufacturability

# Run the demo
./demo.sh
```

## What you'll see

- **Console output**: Step-by-step progress of starting services and submitting analysis
- **Analysis results**: JSON output with manufacturability assessment
- **3D visualization**: Either a web interface at http://localhost:8501 or a PNG screenshot

## Services started

- **Redis**: Database and message broker (localhost:6379)
- **FastAPI**: REST API server (http://localhost:8000)
- **Celery**: Background task worker
- **Streamlit** (optional): Web UI for 3D visualization (http://localhost:8501)

## Stopping the demo

```bash
# Stop all services
./stop_project.sh
```

## Requirements

- Conda environment `auto_eval_manuf` with all dependencies installed
- FlandersMake_part-Merger.stl file in the `data/` directory
- For full 3D visualization: `stpyvista` package (install with `pip install stpyvista`)

## Troubleshooting

- If services fail to start, check that the conda environment is properly configured
- If 3D visualization doesn't work, install `stpyvista` and restart
- Check log files in the project root for detailed error messages