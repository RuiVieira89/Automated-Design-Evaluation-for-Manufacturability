#!/bin/bash

# Automated Design Evaluation for Manufacturability - Project Startup Script
# This script starts all necessary services for the system

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="auto_eval_manuf"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAD Design Evaluation System Startup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if conda is available
echo -e "${YELLOW}[1/7] Checking conda installation...${NC}"
if ! command -v conda &> /dev/null; then
    echo -e "${RED}Error: conda is not installed or not in PATH${NC}"
    exit 1
fi
echo -e "${GREEN}✓ conda found${NC}\n"

# Activate conda environment
echo -e "${YELLOW}[2/7] Activating conda environment: $CONDA_ENV${NC}"
source "$(conda info --base)/etc/profile.d/conda.sh"
if ! conda activate "$CONDA_ENV" 2>/dev/null; then
    echo -e "${RED}Error: Failed to activate conda environment '$CONDA_ENV'${NC}"
    echo -e "${YELLOW}Available environments:${NC}"
    conda env list
    exit 1
fi
echo -e "${GREEN}✓ Conda environment activated${NC}\n"

# Set Python path
echo -e "${YELLOW}[3/7] Setting up environment variables...${NC}"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_DB_BROKER="${REDIS_DB_BROKER:-1}"
export REDIS_DB_BACKEND="${REDIS_DB_BACKEND:-2}"
export FASTAPI_HOST="${FASTAPI_HOST:-0.0.0.0}"
export FASTAPI_PORT="${FASTAPI_PORT:-8000}"
export CELERY_BROKER_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_BROKER}"
export CELERY_RESULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_BACKEND}"
echo -e "${GREEN}✓ Environment variables set${NC}\n"

# Check Redis availability
echo -e "${YELLOW}[4/7] Checking Redis server...${NC}"
if ! command -v redis-server &> /dev/null; then
    echo -e "${RED}Error: redis-server is not installed${NC}"
    echo -e "${YELLOW}Install Redis with: conda install -c conda-forge redis${NC}"
    exit 1
fi

# Start Redis server
if redis-cli ping &> /dev/null; then
    echo -e "${YELLOW}⚠ Redis is already running${NC}"
else
    echo -e "${YELLOW}Starting Redis server...${NC}"
    redis-server --daemonize yes --logfile "$PROJECT_ROOT/redis.log"
    sleep 2
    if redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✓ Redis server started${NC}"
    else
        echo -e "${RED}Error: Failed to start Redis server${NC}"
        exit 1
    fi
fi
echo -e ""

# Start FastAPI server
echo -e "${YELLOW}[5/7] Starting FastAPI server...${NC}"
cd "$PROJECT_ROOT/synchronous_request_plane_FastAPI"
python fastapi_app.py > "$PROJECT_ROOT/fastapi.log" 2>&1 &
FASTAPI_PID=$!
sleep 3

if kill -0 $FASTAPI_PID 2> /dev/null; then
    echo -e "${GREEN}✓ FastAPI server started (PID: $FASTAPI_PID)${NC}"
    echo -e "${GREEN}  API available at: http://localhost:$FASTAPI_PORT${NC}"
else
    echo -e "${RED}Error: Failed to start FastAPI server${NC}"
    cat "$PROJECT_ROOT/fastapi.log"
    exit 1
fi
echo -e ""

# Optionally start Celery workers
echo -e "${YELLOW}[6/7] Celery workers setup...${NC}"
if [ "$START_CELERY" = "true" ] || [ "$1" = "--with-celery" ]; then
    echo -e "${YELLOW}Starting Celery worker...${NC}"
    celery -A celery_tasks worker --loglevel=info > "$PROJECT_ROOT/celery.log" 2>&1 &
    CELERY_PID=$!
    sleep 2
    
    if kill -0 $CELERY_PID 2> /dev/null; then
        echo -e "${GREEN}✓ Celery worker started (PID: $CELERY_PID)${NC}"
    else
        echo -e "${RED}Warning: Failed to start Celery worker${NC}"
        echo -e "${YELLOW}You can start it manually with:${NC}"
        echo -e "${YELLOW}  cd synchronous_request_plane_FastAPI${NC}"
        echo -e "${YELLOW}  celery -A celery_tasks worker --loglevel=info${NC}"
    fi
else
    echo -e "${YELLOW}Celery workers not started (use --with-celery to enable)${NC}"
fi
echo -e ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ System startup complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${BLUE}Quick Start:${NC}"
echo -e "  1. Test the API (health check):"
echo -e "     curl http://localhost:$FASTAPI_PORT/health"
echo -e ""
echo -e "  2. Submit an analysis with a sample file:"
echo -e "     curl -X POST http://localhost:$FASTAPI_PORT/analyze \\"
echo -e "       -F \"file=@${PROJECT_ROOT}/data/cube.off\" \\"
echo -e "       -F 'process_type=single'"
echo -e ""
echo -e "  3. Or with the FlandersMake part (STL format):"
echo -e "     curl -X POST http://localhost:$FASTAPI_PORT/analyze \\"
echo -e "       -F \"file=@${PROJECT_ROOT}/data/FlandersMake_part-Merger.stl\" \\"
echo -e "       -F 'process_type=single'"
echo -e ""
echo -e "  4. Check job status (use job_id from response above):"
echo -e "     curl http://localhost:$FASTAPI_PORT/job/{job_id}"
echo -e ""

echo -e "${BLUE}Services:${NC}"
echo -e "  • Redis:   $REDIS_HOST:$REDIS_PORT"
echo -e "  • FastAPI: http://localhost:$FASTAPI_PORT"
echo -e "  • Docs:    http://localhost:$FASTAPI_PORT/docs"
echo -e ""

echo -e "${BLUE}Logs:${NC}"
echo -e "  • FastAPI: ${YELLOW}tail -f $PROJECT_ROOT/fastapi.log${NC}"
echo -e "  • Redis:   ${YELLOW}tail -f $PROJECT_ROOT/redis.log${NC}"
echo -e ""

if [ "$START_CELERY" = "true" ] || [ "$1" = "--with-celery" ]; then
    echo -e "  • Celery:  ${YELLOW}tail -f $PROJECT_ROOT/celery.log${NC}"
fi

echo -e ""
echo -e "${BLUE}Shutdown:${NC}"
echo -e "  • Run: ${YELLOW}bash stop_project.sh${NC}"
echo -e ""

echo -e "${BLUE}To test the API in a new terminal, use:${NC}"
echo -e ""
echo -e "  # Health check:"
echo -e "  curl http://localhost:8000/health"
echo -e ""
echo -e "  # Submit analysis with cube.off:"
echo -e "  curl -X POST http://localhost:8000/analyze \\"
echo -e "    -F \"file=@${PROJECT_ROOT}/data/cube.off\" \\"
echo -e "    -F 'process_type=single'"
echo -e ""
echo -e "  # Submit analysis with STL file:"
echo -e "  curl -X POST http://localhost:8000/analyze \\"
echo -e "    -F \"file=@${PROJECT_ROOT}/data/FlandersMake_part-Merger.stl\" \\"
echo -e "    -F 'process_type=single'"
echo -e ""
echo -e "  # Check job status (replace with your job_id):"
echo -e "  curl http://localhost:8000/job/{job_id}"
echo -e ""

echo -e "${YELLOW}Project root: $PROJECT_ROOT${NC}"
echo -e "${YELLOW}Environment: $CONDA_ENV${NC}\n"
