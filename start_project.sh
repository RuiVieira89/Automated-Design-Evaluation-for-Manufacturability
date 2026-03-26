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
STL_FILE="${PROJECT_ROOT}/data/FlandersMake_part-Merger.stl"
FALLBACK_FILE="${PROJECT_ROOT}/data/cube.off"

ENABLE_CELERY="${START_CELERY:-false}"
ANALYSIS_FILE_ARG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --with-celery)
            ENABLE_CELERY="true"
            shift
            ;;
        --file)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: --file requires a path argument${NC}"
                exit 1
            fi
            ANALYSIS_FILE_ARG="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: bash start_project.sh [--with-celery] [--file <path>] [file_path]"
            echo ""
            echo "Examples:"
            echo "  bash start_project.sh --with-celery"
            echo "  bash start_project.sh --file data/cube.off"
            echo "  bash start_project.sh data/FlandersMake_part-Merger.stl"
            exit 0
            ;;
        -*)
            echo -e "${RED}Error: Unknown option '$1'${NC}"
            echo "Run with --help to see supported arguments."
            exit 1
            ;;
        *)
            ANALYSIS_FILE_ARG="$1"
            shift
            ;;
    esac
done

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
if [ "$ENABLE_CELERY" = "true" ]; then
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

# Run analysis and open browser like demo.sh
echo -e "${YELLOW}[7/7] Running sample analysis and opening visualization...${NC}"

ANALYSIS_FILE=""
if [ -n "$ANALYSIS_FILE_ARG" ]; then
    if [ -f "$ANALYSIS_FILE_ARG" ]; then
        ANALYSIS_FILE="$ANALYSIS_FILE_ARG"
    elif [ -f "${PROJECT_ROOT}/$ANALYSIS_FILE_ARG" ]; then
        ANALYSIS_FILE="${PROJECT_ROOT}/$ANALYSIS_FILE_ARG"
    else
        echo -e "${RED}Error: Analysis file not found: $ANALYSIS_FILE_ARG${NC}"
        exit 1
    fi
elif [ -f "$STL_FILE" ]; then
    ANALYSIS_FILE="$STL_FILE"
elif [ -f "$FALLBACK_FILE" ]; then
    ANALYSIS_FILE="$FALLBACK_FILE"
else
    echo -e "${RED}Error: No sample file found for analysis${NC}"
    echo -e "${YELLOW}Expected one of:${NC}"
    echo -e "${YELLOW}  $STL_FILE${NC}"
    echo -e "${YELLOW}  $FALLBACK_FILE${NC}"
    exit 1
fi

echo -e "${YELLOW}Checking API health...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:$FASTAPI_PORT/health)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✓ API health check passed${NC}"
else
    echo -e "${RED}Error: API health check failed${NC}"
    echo -e "${YELLOW}Response: $HEALTH_RESPONSE${NC}"
    exit 1
fi

if [ "$ENABLE_CELERY" != "true" ]; then
    echo -e "${YELLOW}Celery worker is required for async analysis; starting it automatically...${NC}"
    celery -A celery_tasks worker --loglevel=info > "$PROJECT_ROOT/celery.log" 2>&1 &
    CELERY_PID=$!
    sleep 2
    if kill -0 $CELERY_PID 2> /dev/null; then
        echo -e "${GREEN}✓ Celery worker started (PID: $CELERY_PID)${NC}"
        ENABLE_CELERY="true"
    else
        echo -e "${RED}Error: Failed to start Celery worker${NC}"
        echo -e "${YELLOW}Check logs: tail -f $PROJECT_ROOT/celery.log${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}Submitting analysis job...${NC}"
echo -e "${BLUE}File: $(basename "$ANALYSIS_FILE")${NC}"
echo -e "${BLUE}Size: $(du -h "$ANALYSIS_FILE" | cut -f1)${NC}"

ANALYSIS_RESPONSE=$(curl -s -X POST http://localhost:$FASTAPI_PORT/analyze \
  -F "file=@$ANALYSIS_FILE" \
  -F "process_type=single")

echo -e "${GREEN}✓ Analysis job submitted${NC}"
echo -e "${BLUE}Response: $ANALYSIS_RESPONSE${NC}"

JOB_ID=$(echo "$ANALYSIS_RESPONSE" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$JOB_ID" ]; then
    echo -e "${RED}Error: Could not extract job_id from response${NC}"
    exit 1
fi

MAX_POLLS=30
POLL_COUNT=0
JOB_STATUS=""

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    echo -e "${YELLOW}Checking job status (attempt $((POLL_COUNT+1))/$MAX_POLLS)...${NC}"
    JOB_STATUS=$(curl -s http://localhost:$FASTAPI_PORT/job/$JOB_ID)

    STATUS=$(echo "$JOB_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', ''))" 2>/dev/null)
    if [ -z "$STATUS" ]; then
        STATUS=$(echo "$JOB_STATUS" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
    fi

    case "$STATUS" in
        "SUCCESS")
            echo -e "${GREEN}✓ Analysis completed successfully!${NC}"
            break
            ;;
        "FAILURE")
            echo -e "${RED}✗ Analysis failed${NC}"
            ERROR=$(echo "$JOB_STATUS" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
            echo -e "${RED}Error: $ERROR${NC}"
            exit 1
            ;;
        "PENDING"|"RUNNING")
            echo -e "${YELLOW}⏳ Status: $STATUS${NC}"
            PROGRESS=$(echo "$JOB_STATUS" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
            if [ -n "$PROGRESS" ]; then
                echo -e "${YELLOW}Progress: ${PROGRESS}%${NC}"
            fi
            ;;
        *)
            echo -e "${YELLOW}Status: $STATUS${NC}"
            ;;
    esac

    if [ "$STATUS" != "SUCCESS" ]; then
        sleep 3
        POLL_COUNT=$((POLL_COUNT+1))
    fi
done

if [ $POLL_COUNT -ge $MAX_POLLS ]; then
    echo -e "${RED}Error: Analysis timed out after $MAX_POLLS attempts${NC}"
    exit 1
fi

VIZ_URL="http://localhost:${FASTAPI_PORT}/job/${JOB_ID}/visualization"
echo -e "${YELLOW}Checking for 3D visualization...${NC}"
VIZ_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$VIZ_URL")

if [ "$VIZ_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Interactive 3D visualization ready${NC}"
    echo -e "${GREEN}  URL: $VIZ_URL${NC}"
    echo -e "${YELLOW}Opening browser - rotate the part by dragging, scroll to zoom.${NC}"
    xdg-open "$VIZ_URL" 2>/dev/null \
      || open "$VIZ_URL" 2>/dev/null \
      || python3 -m webbrowser "$VIZ_URL" 2>/dev/null \
      || echo -e "${YELLOW}Could not open browser automatically. Open manually: $VIZ_URL${NC}"
else
    echo -e "${YELLOW}⚠ Visualization endpoint returned HTTP $VIZ_STATUS${NC}"
    echo -e "${YELLOW}  The HTML file may not have been generated (check celery.log).${NC}"
    echo -e "${YELLOW}  You can retry manually: curl $VIZ_URL${NC}"
fi

echo -e ""
echo -e "${BLUE}Analysis Job:${NC}"
echo -e "  • Job ID: $JOB_ID"
echo -e "  • Result: http://localhost:$FASTAPI_PORT/job/$JOB_ID"
echo -e "  • 3D Visualization: $VIZ_URL"
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

if [ "$ENABLE_CELERY" = "true" ]; then
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
