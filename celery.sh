#!/bin/bash
# celery.sh - Start Celery services for local development
# Usage: ./celery.sh [command]
#
# Commands:
#   start     - Start Redis + Celery worker + Celery beat (default)
#   stop      - Stop all Celery services
#   logs      - Show Celery logs
#   status    - Check service status

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

COMMAND=${1:-start}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: Virtual environment not found at .venv/${NC}"
    echo "Create it with: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Load environment variables from .env file
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ Loading environment from .env${NC}"
    # Export all variables from .env (handling quotes and comments)
    set -a
    source <(grep -v '^#' .env | grep -v '^$' | while read -r line; do
        # Handle lines with = but no value
        if [[ "$line" == *=* ]]; then
            key="${line%%=*}"
            value="${line#*=}"
            # Remove surrounding quotes if present
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"
            echo "$key=\"$value\""
        fi
    done)
    set +a
else
    echo -e "${YELLOW}Warning: .env file not found, using default environment${NC}"
fi

# Check for Redis
check_redis() {
    if ! command -v redis-cli &> /dev/null; then
        echo -e "${RED}Redis not found. Install it:${NC}"
        echo "  Ubuntu/Debian: sudo apt install redis-server"
        echo "  macOS: brew install redis"
        echo "  Arch: sudo pacman -S redis"
        exit 1
    fi

    if ! redis-cli ping &> /dev/null; then
        echo -e "${YELLOW}Redis not running. Starting Redis...${NC}"
        if command -v systemctl &> /dev/null; then
            sudo systemctl start redis
        elif command -v brew services &> /dev/null; then
            brew services start redis
        else
            redis-server --daemonize yes
        fi
        sleep 2
        if redis-cli ping &> /dev/null; then
            echo -e "${GREEN}✓ Redis started${NC}"
        else
            echo -e "${RED}Failed to start Redis${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Redis is running${NC}"
    fi
}

start_celery() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Starting Celery Services for HNA Acadex${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Check Redis
    check_redis

    # Set environment
    export DJANGO_SETTINGS_MODULE=config.settings

    # Convert relative Firebase credentials path to absolute
    if [ -n "$FIREBASE_CREDENTIALS_PATH" ]; then
        # If it's a relative path starting with ./, make it absolute
        if [[ "$FIREBASE_CREDENTIALS_PATH" == ./* ]]; then
            export FIREBASE_CREDENTIALS_PATH="$SCRIPT_DIR/${FIREBASE_CREDENTIALS_PATH#./}"
        fi
        echo -e "${GREEN}✓ Firebase credentials: $FIREBASE_CREDENTIALS_PATH${NC}"
    else
        echo -e "${YELLOW}⚠ FIREBASE_CREDENTIALS_PATH not set - push notifications disabled${NC}"
    fi

    # Create logs directory
    mkdir -p logs

    # Start Celery Worker
    echo -e "${YELLOW}Starting Celery Worker...${NC}"
    celery -A config worker -l INFO --concurrency=2 \
        > logs/celery-worker.log 2>&1 &
    WORKER_PID=$!
    echo $WORKER_PID > logs/celery-worker.pid
    echo -e "${GREEN}✓ Celery Worker started (PID: $WORKER_PID)${NC}"

    # Start Celery Beat
    echo -e "${YELLOW}Starting Celery Beat...${NC}"
    celery -A config beat -l INFO \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler \
        > logs/celery-beat.log 2>&1 &
    BEAT_PID=$!
    echo $BEAT_PID > logs/celery-beat.pid
    echo -e "${GREEN}✓ Celery Beat started (PID: $BEAT_PID)${NC}"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}All Celery services running!${NC}"
    echo ""
    echo "Logs:"
    echo "  Worker: logs/celery-worker.log"
    echo "  Beat:   logs/celery-beat.log"
    echo ""
    echo "Commands:"
    echo "  ./celery.sh status  - Check service status"
    echo "  ./celery.sh logs     - Tail all logs"
    echo "  ./celery.sh stop    - Stop all services"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

stop_celery() {
    echo -e "${YELLOW}Stopping Celery services...${NC}"

    # Stop Worker
    if [ -f logs/celery-worker.pid ]; then
        WORKER_PID=$(cat logs/celery-worker.pid)
        if kill -0 $WORKER_PID 2>/dev/null; then
            kill $WORKER_PID
            echo -e "${GREEN}✓ Celery Worker stopped${NC}"
        fi
        rm logs/celery-worker.pid
    fi

    # Stop Beat
    if [ -f logs/celery-beat.pid ]; then
        BEAT_PID=$(cat logs/celery-beat.pid)
        if kill -0 $BEAT_PID 2>/dev/null; then
            kill $BEAT_PID
            echo -e "${GREEN}✓ Celery Beat stopped${NC}"
        fi
        rm logs/celery-beat.pid
    fi

    echo -e "${GREEN}All Celery services stopped${NC}"
}

show_logs() {
    echo -e "${BLUE}Tailing Celery logs (Ctrl+C to exit)...${NC}"
    echo ""
    tail -f logs/celery-worker.log logs/celery-beat.log
}

show_status() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Celery Service Status${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Check Redis
    echo -e "${YELLOW}Redis:${NC}"
    if redis-cli ping &> /dev/null; then
        echo -e "  ${GREEN}✓ Running${NC}"
    else
        echo -e "  ${RED}✗ Not running${NC}"
    fi

    # Check Celery Worker
    echo -e "${YELLOW}Celery Worker:${NC}"
    if [ -f logs/celery-worker.pid ]; then
        WORKER_PID=$(cat logs/celery-worker.pid)
        if kill -0 $WORKER_PID 2>/dev/null; then
            echo -e "  ${GREEN}✓ Running (PID: $WORKER_PID)${NC}"
        else
            echo -e "  ${RED}✗ Stopped (stale PID file)${NC}"
        fi
    else
        echo -e "  ${RED}✗ Not running${NC}"
    fi

    # Check Celery Beat
    echo -e "${YELLOW}Celery Beat:${NC}"
    if [ -f logs/celery-beat.pid ]; then
        BEAT_PID=$(cat logs/celery-beat.pid)
        if kill -0 $BEAT_PID 2>/dev/null; then
            echo -e "  ${GREEN}✓ Running (PID: $BEAT_PID)${NC}"
        else
            echo -e "  ${RED}✗ Stopped (stale PID file)${NC}"
        fi
    else
        echo -e "  ${RED}✗ Not running${NC}"
    fi

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Show active tasks
    echo ""
    echo -e "${YELLOW}Registered Tasks:${NC}"
    celery -A config inspect registered 2>/dev/null | head -30 || echo "  Unable to query (worker may be starting)"
}

case $COMMAND in
    start)
        start_celery
        ;;
    stop)
        stop_celery
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|logs|status}"
        exit 1
        ;;
esac