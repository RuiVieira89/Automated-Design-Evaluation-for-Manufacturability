#!/bin/bash

# Automated Design Evaluation for Manufacturability - Project Shutdown Script
# This script stops all running services

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAD Design Evaluation System Shutdown${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kill FastAPI
echo -e "${YELLOW}Stopping FastAPI server...${NC}"
pkill -f "python fastapi_app.py" || true
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ FastAPI server stopped${NC}"
else
    echo -e "${YELLOW}⚠ FastAPI server was not running${NC}"
fi

# Kill Celery worker
echo -e "${YELLOW}Stopping Celery worker...${NC}"
pkill -f "celery -A celery_tasks worker" || true
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Celery worker stopped${NC}"
else
    echo -e "${YELLOW}⚠ Celery worker was not running${NC}"
fi

# Stop Redis
echo -e "${YELLOW}Stopping Redis server...${NC}"
if command -v redis-cli &> /dev/null; then
    redis-cli shutdown &> /dev/null || redis-cli -n 0 SHUTDOWN NOSAVE &> /dev/null || true
    sleep 1
    if ! redis-cli ping &> /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis server stopped${NC}"
    else
        echo -e "${YELLOW}⚠ Redis server still running (may require manual intervention)${NC}"
    fi
else
    pkill -f redis-server || true
    echo -e "${GREEN}✓ Redis process terminated${NC}"
fi

echo -e ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All services stopped${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Clean up
echo -e "${YELLOW}Cleaning up...${NC}"
rm -f "$PROJECT_ROOT/fastapi.log" "$PROJECT_ROOT/celery.log"
echo -e "${GREEN}✓ Log files cleaned${NC}\n"

echo -e "${BLUE}To restart the system, run:${NC}"
echo -e "  ${YELLOW}bash start_project.sh${NC}\n"
