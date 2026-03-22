#!/bin/bash

# Automated Design Evaluation for Manufacturability - Full Demo Script
# This script demonstrates the complete system using FlandersMake_part-Merger.stl
# and shows 3D visualization of the analysis results
#
# What this script does:
# 1. Starts Redis, FastAPI, and Celery services
# 2. Submits the FlandersMake STL file for manufacturability analysis
# 3. Polls for analysis completion
# 4. Displays results and starts 3D visualization
#
# Usage: ./demo.sh
# Requirements: conda environment 'auto_eval_manuf' with all dependencies installed

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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAD Design Evaluation System - Full Demo${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if STL file exists
if [ ! -f "$STL_FILE" ]; then
    echo -e "${RED}Error: STL file not found: $STL_FILE${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Found STL file: $(basename "$STL_FILE")${NC}\n"

# Check if conda is available
echo -e "${YELLOW}[1/8] Checking conda installation...${NC}"
if ! command -v conda &> /dev/null; then
    echo -e "${RED}Error: conda is not installed or not in PATH${NC}"
    exit 1
fi
echo -e "${GREEN}✓ conda found${NC}\n"

# Activate conda environment
echo -e "${YELLOW}[2/8] Activating conda environment: $CONDA_ENV${NC}"
source "$(conda info --base)/etc/profile.d/conda.sh"
if ! conda activate "$CONDA_ENV" 2>/dev/null; then
    echo -e "${RED}Error: Failed to activate conda environment '$CONDA_ENV'${NC}"
    echo -e "${YELLOW}Available environments:${NC}"
    conda env list
    exit 1
fi
echo -e "${GREEN}✓ Conda environment activated${NC}\n"

# Set Python path and environment variables
echo -e "${YELLOW}[3/8] Setting up environment variables...${NC}"
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
echo -e "${YELLOW}[4/8] Checking Redis server...${NC}"
if ! command -v redis-server &> /dev/null; then
    echo -e "${RED}Error: redis-server is not installed${NC}"
    echo -e "${YELLOW}Install Redis with: conda install -c conda-forge redis${NC}"
    exit 1
fi

# Start Redis server if not running
if ! redis-cli ping &> /dev/null; then
    echo -e "${YELLOW}Starting Redis server...${NC}"
    redis-server --daemonize yes --logfile "$PROJECT_ROOT/redis.log"
    sleep 2
    if redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✓ Redis server started${NC}"
    else
        echo -e "${RED}Error: Failed to start Redis server${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Redis server already running${NC}"
fi
echo -e ""

# Start FastAPI server
echo -e "${YELLOW}[5/8] Starting FastAPI server...${NC}"
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

# Start Celery worker
echo -e "${YELLOW}[6/8] Starting Celery worker...${NC}"
celery -A celery_tasks worker --loglevel=info > "$PROJECT_ROOT/celery.log" 2>&1 &
CELERY_PID=$!
sleep 3

if kill -0 $CELERY_PID 2> /dev/null; then
    echo -e "${GREEN}✓ Celery worker started (PID: $CELERY_PID)${NC}"
else
    echo -e "${YELLOW}Warning: Failed to start Celery worker${NC}"
    echo -e "${YELLOW}You can start it manually with:${NC}"
    echo -e "${YELLOW}  cd synchronous_request_plane_FastAPI${NC}"
    echo -e "${YELLOW}  celery -A celery_tasks worker --loglevel=info${NC}"
fi
echo -e ""

# Test health check
echo -e "${YELLOW}[7/8] Testing API health...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:$FASTAPI_PORT/health)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✓ API health check passed${NC}"
else
    echo -e "${RED}Error: API health check failed${NC}"
    echo -e "${YELLOW}Response: $HEALTH_RESPONSE${NC}"
    exit 1
fi
echo -e ""

# Submit analysis job
echo -e "${YELLOW}[8/8] Submitting FlandersMake part for analysis...${NC}"
echo -e "${BLUE}File: $(basename "$STL_FILE")${NC}"
echo -e "${BLUE}Size: $(du -h "$STL_FILE" | cut -f1)${NC}"

ANALYSIS_RESPONSE=$(curl -s -X POST http://localhost:$FASTAPI_PORT/analyze \
  -F "file=@$STL_FILE" \
  -F "process_type=single")

echo -e "${GREEN}✓ Analysis job submitted${NC}"
echo -e "${BLUE}Response: $ANALYSIS_RESPONSE${NC}"

# Extract job_id from response
JOB_ID=$(echo "$ANALYSIS_RESPONSE" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}Error: Could not extract job_id from response${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Job ID: $JOB_ID${NC}"
echo -e ""

# Poll for job completion
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Polling for analysis results...${NC}"
echo -e "${BLUE}========================================${NC}\n"

MAX_POLLS=30
POLL_COUNT=0

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    echo -e "${YELLOW}Checking job status (attempt $((POLL_COUNT+1))/$MAX_POLLS)...${NC}"

    JOB_STATUS=$(curl -s http://localhost:$FASTAPI_PORT/job/$JOB_ID)

    # Extract only the top-level status field (not nested ones in result)
    STATUS=$(echo "$JOB_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', ''))" 2>/dev/null)
    
    # Fallback to grep if python fails
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

echo -e ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Analysis Results${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Display results
echo "$JOB_STATUS" | python3 -m json.tool

echo -e ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}3D Visualization${NC}"
echo -e "${BLUE}========================================${NC}\n"

VIZ_URL="http://localhost:${FASTAPI_PORT}/job/${JOB_ID}/visualization"

# Verify the visualization endpoint is available before opening
echo -e "${YELLOW}Checking for 3D visualization...${NC}"
VIZ_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$VIZ_URL")

if [ "$VIZ_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Interactive 3D visualization ready${NC}"
    echo -e "${GREEN}  URL: $VIZ_URL${NC}"
    echo -e "${YELLOW}Opening browser — rotate the part by dragging, scroll to zoom.${NC}"
    echo -e ""
    # Try platform-specific open commands in priority order
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
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Demo Complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${BLUE}Services Running:${NC}"
echo -e "  • Redis:   $REDIS_HOST:$REDIS_PORT"
echo -e "  • FastAPI: http://localhost:$FASTAPI_PORT"
echo -e "  • Celery:  Running in background"
echo -e ""

echo -e "${BLUE}Job Information:${NC}"
echo -e "  • Job ID: $JOB_ID"
echo -e "  • STL File: $(basename "$STL_FILE")"
echo -e "  • Results API:    http://localhost:$FASTAPI_PORT/job/$JOB_ID"
echo -e "  • 3D Visualization: $VIZ_URL"
echo -e ""
echo -e "${BLUE}To stop all services, run:${NC}"
echo -e "  bash stop_project.sh"
echo -e ""

echo -e "${YELLOW}Press Ctrl+C to exit this script (services will continue running)${NC}"
echo -e ""

# Wait for user to see results
trap 'echo -e "\n${YELLOW}Demo script exiting... Services are still running.${NC}"' INT
wait