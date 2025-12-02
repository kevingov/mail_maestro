"""
📧 Email Tracking System with Railway API
Local version that sends tracking data to Railway PostgreSQL database
"""

import sqlite3
import uuid
import datetime
from io import BytesIO
import base64
from PIL import Image
import requests
import json

class EmailTracker:
    def __init__(self, db_path='email_tracking.db'):
        """Initialize the Email Tracker with Railway API integration."""
        self.db_path = db_path
        self.railway_url = "https://web-production-6dfbd.up.railway.app"
        self.init_database()
    
    def init_database(self):
        """Create the local tracking database and tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Email tracking table (local backup)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_id TEXT UNIQUE NOT NULL,
                recipient_email TEXT NOT NULL,
                sender_email TEXT,
                subject TEXT,
                campaign_name TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                opened_at TIMESTAMP,
                open_count INTEGER DEFAULT 0,
                last_opened_at TIMESTAMP,
                user_agent TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Local email tracking database initialized")
    
    def generate_tracking_id(self):
        """Generate a unique tracking ID."""
        return str(uuid.uuid4())
    
    def create_tracking_pixel(self):
        """Create a 1x1 transparent PNG pixel."""
        # Create a 1x1 transparent image
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()
    
    def track_email_sent(self, recipient_email, sender_email=None, subject=None, campaign_name=None, variant_endpoint=None):
        """
        Register a new email for tracking via Railway API.
        Returns tracking_id for embedding in email.
        """
        tracking_id = self.generate_tracking_id()
        
        # Send to Railway API
        try:
            response = requests.post(f"{self.railway_url}/api/track-send", 
                json={
                    'tracking_id': tracking_id,
                    'recipient_email': recipient_email,
                    'sender_email': sender_email,
                    'subject': subject,
                    'campaign_name': campaign_name,
                    'variant_endpoint': variant_endpoint
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                tracking_id = data.get('tracking_id', tracking_id)
                print(f"📧 Email tracked on Railway: {tracking_id}")
            else:
                print(f"⚠️ Railway API error: {response.status_code} - {response.text}")
                print(f"📧 Email tracked locally only: {tracking_id}")
        except Exception as e:
            print(f"⚠️ Railway API error: {e}")
            print(f"📧 Email tracked locally only: {tracking_id}")
        
        # Store locally as backup
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (tracking_id, recipient_email, sender_email, subject, campaign_name))
        
        conn.commit()
        conn.close()
        
        return tracking_id
    
    def add_tracking_to_email(self, html_content, tracking_id, base_url="https://web-production-6dfbd.up.railway.app"):
        """
        Add tracking pixel to email HTML content.
        """
        tracking_pixel = f'<img src="{base_url}/track/{tracking_id}" width="1" height="1" style="display:none;" alt="" />'
        
        # Add tracking pixel before closing body tag
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', f'{tracking_pixel}\n</body>')
        else:
            # If no body tag, append to end
            html_content += f'\n{tracking_pixel}'
        
        return html_content
    
    def track_email_open(self, tracking_id, user_agent="", ip_address="", referer=""):
        """
        Track when an email is opened.
        This will be handled by the Railway tracking pixel.
        """
        # The Railway tracking pixel handles this automatically
        print(f"📧 Email open will be tracked by Railway: {tracking_id}")
        return True
    
    def get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def get_railway_stats(self):
        """Get tracking statistics from Railway."""
        try:
            response = requests.get(f"{self.railway_url}/api/stats", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Railway API error: {response.status_code}'}
        except Exception as e:
            return {'error': f'Railway API error: {e}'}
