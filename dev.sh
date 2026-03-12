#!/bin/bash
# Development server script for HNA Acadex Backend
# Usage: ./dev.sh [port]

PORT=${1:-8000}

echo "🚀 Starting HNA Acadex Backend Development Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📡 Server will run on: http://0.0.0.0:$PORT"
echo "📱 Android Emulator API URL: http://10.0.2.2:$PORT/api"
echo "💻 Local API URL: http://localhost:$PORT/api"
echo ""
echo "🔧 Environment: Development (DEBUG=1)"
echo "📧 Email backend: Console (emails printed to terminal)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Run migrations if needed
echo "Checking for pending migrations..."
python manage.py migrate --run-syncdb 2>/dev/null

echo ""
echo "Starting server..."
echo "Press Ctrl+C to stop"
echo ""

# Run development server on all interfaces
python manage.py runserver 0.0.0.0:$PORT