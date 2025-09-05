"""
🔧 Tracking Configuration
Configure your tracking server for public access
"""

import os
import socket

def get_local_ip():
    """Get your local IP address for network access"""
    try:
        # Connect to a remote server to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"

# Configuration
TRACKING_CONFIG = {
    # Use your local IP instead of localhost for external access
    'BASE_URL': f"http://{get_local_ip()}:5001",
    'HOST': '0.0.0.0',  # Allow external connections
    'PORT': 5001,
    'DEBUG': True
}

# Alternative: If you have a domain or want to use ngrok
# TRACKING_CONFIG['BASE_URL'] = "https://your-domain.ngrok.io"

print(f"🌐 Tracking will be available at: {TRACKING_CONFIG['BASE_URL']}")
print(f"📱 Make sure your phone is on the same WiFi network")
print(f"🔧 If using ngrok, update BASE_URL to your ngrok URL")
