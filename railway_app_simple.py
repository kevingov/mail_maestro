"""
🚂 Ultra-simple Railway Email Tracking App
Minimal version without database dependencies for testing
"""

import os
from flask import Flask, Response, request, jsonify
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

def create_simple_pixel():
    """Create a simple 1x1 transparent pixel"""
    img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    img_io = BytesIO()
    img.save(img_io, format='PNG')
    img_io.seek(0)
    return img_io.getvalue()

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
    """Serve tracking pixel and log the request."""
    # Log the tracking request
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.remote_addr
    referer = request.headers.get('Referer', '')
    
    print(f"📧 Email opened! Tracking ID: {tracking_id}")
    print(f"🌐 IP: {ip_address}")
    print(f"🔍 User Agent: {user_agent}")
    print(f"📄 Referer: {referer}")
    
    # Create and return the pixel
    pixel_data = create_simple_pixel()
    
    return Response(
        pixel_data,
        mimetype='image/png',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Email Tracking Pixel',
        'version': '1.0.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
