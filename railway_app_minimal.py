"""
🚂 Minimal Railway Email Tracking App
Only includes essential tracking pixel functionality for Railway deployment
"""

import os
import sqlite3
from flask import Flask, Response, request, jsonify
from email_tracker import EmailTracker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize email tracker
tracker = EmailTracker()

@app.route('/')
def home():
    """Home page with service info."""
    return jsonify({
        'service': 'Email Tracking Pixel',
        'status': 'running',
        'version': '1.0.0',
        'endpoints': {
            'tracking_pixel': '/track/<tracking_id>',
            'health_check': '/api/health'
        }
    })

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """
    Serve the tracking pixel and record email open.
    This is the main endpoint that email clients will call.
    """
    try:
        # Get request information
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Log the tracking attempt
        logger.info(f"📧 Tracking pixel accessed: {tracking_id}")
        
        # Record the email open
        success = tracker.track_email_open(tracking_id, user_agent, ip_address, referer)
        
        if success:
            logger.info(f"✅ Successfully tracked email open for: {tracking_id}")
        else:
            logger.warning(f"⚠️ Failed to track email open for: {tracking_id}")
        
        # Create and return a 1x1 transparent pixel
        pixel_data = tracker.create_tracking_pixel()
        
        return Response(
            pixel_data,
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error in track_pixel: {str(e)}")
        # Still return a pixel even if tracking fails
        pixel_data = tracker.create_tracking_pixel()
        return Response(
            pixel_data,
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Access-Control-Allow-Origin': '*'
            }
        )

@app.route('/api/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Simple health check without database connection
        return jsonify({
            'status': 'healthy',
            'service': 'email-tracking',
            'version': '1.0.0',
            'message': 'Tracking pixel service is running'
        })
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Railway will set the PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Railway email tracking server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
