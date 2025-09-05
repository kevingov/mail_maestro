#!/bin/bash

echo "🚀 Starting Public Email Tracking Server"
echo "========================================"

# Check if required files exist
if [ ! -f "tracking_dashboard_public.py" ]; then
    echo "❌ tracking_dashboard_public.py not found!"
    exit 1
fi

if [ ! -f "tracking_config.py" ]; then
    echo "❌ tracking_config.py not found!"
    exit 1
fi

# Show configuration
echo "📋 Configuration:"
python3 -c "from tracking_config import TRACKING_CONFIG; print(f'🌐 Base URL: {TRACKING_CONFIG[\"BASE_URL\"]}'); print(f'🔌 Host: {TRACKING_CONFIG[\"HOST\"]}'); print(f'🔌 Port: {TRACKING_CONFIG[\"PORT\"]}')"

echo ""
echo "📱 Instructions for testing on your phone:"
echo "1. Make sure your phone is on the same WiFi network"
echo "2. The server will be accessible at the Base URL above"
echo "3. Test with: python3 test_public_tracking.py"
echo ""

# Start the server
echo "🚀 Starting server..."
python3 tracking_dashboard_public.py
