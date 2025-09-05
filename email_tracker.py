"""
📧 Email Tracking System with Pixel Tracking
Track email opens, clicks, and engagement metrics using invisible tracking pixels.
"""

import sqlite3
import uuid
import datetime
from io import BytesIO
import base64
from PIL import Image

class EmailTracker:
    def __init__(self, db_path='email_tracking.db'):
        """Initialize the Email Tracker with database setup."""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Create the tracking database and tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Email tracking table
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
        
        # Email opens table (for tracking multiple opens)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_opens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_id TEXT NOT NULL,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                ip_address TEXT,
                referer TEXT,
                FOREIGN KEY (tracking_id) REFERENCES email_tracking (tracking_id)
            )
        ''')
        
        # Campaign performance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_performance (
                campaign_name TEXT PRIMARY KEY,
                total_sent INTEGER DEFAULT 0,
                total_opened INTEGER DEFAULT 0,
                unique_opens INTEGER DEFAULT 0,
                open_rate REAL DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Email tracking database initialized")
    
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
    
    def track_email_sent(self, recipient_email, sender_email=None, subject=None, campaign_name=None):
        """
        Register a new email for tracking.
        Returns tracking_id for embedding in email.
        """
        tracking_id = self.generate_tracking_id()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (tracking_id, recipient_email, sender_email, subject, campaign_name))
        
        # Update campaign stats
        if campaign_name:
            cursor.execute('''
                INSERT OR REPLACE INTO campaign_performance (campaign_name, total_sent, unique_opens, total_opened, open_rate, last_updated)
                VALUES (?, 
                    COALESCE((SELECT total_sent FROM campaign_performance WHERE campaign_name = ?), 0) + 1,
                    COALESCE((SELECT unique_opens FROM campaign_performance WHERE campaign_name = ?), 0),
                    COALESCE((SELECT total_opened FROM campaign_performance WHERE campaign_name = ?), 0),
                    COALESCE((SELECT open_rate FROM campaign_performance WHERE campaign_name = ?), 0.0),
                    CURRENT_TIMESTAMP)
            ''', (campaign_name, campaign_name, campaign_name, campaign_name, campaign_name))
        
        conn.commit()
        conn.close()
        
        print(f"📧 Email tracked: {recipient_email} -> {tracking_id}")
        return tracking_id
    
    def track_email_open(self, tracking_id, user_agent=None, ip_address=None, referer=None):
        """Record an email open event."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if tracking_id exists
        cursor.execute('SELECT id, campaign_name, open_count FROM email_tracking WHERE tracking_id = ?', (tracking_id,))
        email_record = cursor.fetchone()
        
        if not email_record:
            conn.close()
            return False
        
        email_id, campaign_name, current_open_count = email_record
        
        # Record the open in email_opens table
        cursor.execute('''
            INSERT INTO email_opens (tracking_id, user_agent, ip_address, referer)
            VALUES (?, ?, ?, ?)
        ''', (tracking_id, user_agent, ip_address, referer))
        
        # Update email_tracking table
        if current_open_count == 0:
            # First open
            cursor.execute('''
                UPDATE email_tracking 
                SET opened_at = CURRENT_TIMESTAMP, open_count = 1, last_opened_at = CURRENT_TIMESTAMP,
                    user_agent = ?, ip_address = ?
                WHERE tracking_id = ?
            ''', (user_agent, ip_address, tracking_id))
            
            # Update campaign unique opens
            if campaign_name:
                cursor.execute('''
                    UPDATE campaign_performance 
                    SET unique_opens = unique_opens + 1, total_opened = total_opened + 1,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE campaign_name = ?
                ''', (campaign_name,))
                
                # Update open rate in a separate query after the counts are updated
                cursor.execute('''
                    UPDATE campaign_performance 
                    SET open_rate = ROUND(unique_opens * 100.0 / total_sent, 2)
                    WHERE campaign_name = ?
                ''', (campaign_name,))
        else:
            # Subsequent opens
            cursor.execute('''
                UPDATE email_tracking 
                SET open_count = open_count + 1, last_opened_at = CURRENT_TIMESTAMP
                WHERE tracking_id = ?
            ''', (tracking_id,))
            
            # Update campaign total opens
            if campaign_name:
                cursor.execute('''
                    UPDATE campaign_performance 
                    SET total_opened = total_opened + 1, last_updated = CURRENT_TIMESTAMP
                    WHERE campaign_name = ?
                ''', (campaign_name,))
        
        conn.commit()
        conn.close()
        
        print(f"📖 Email opened: {tracking_id} (Open #{current_open_count + 1})")
        return True
    
    def add_tracking_to_email(self, html_content, tracking_id, base_url="http://localhost:5001"):
        """
        Add tracking pixel to email HTML content.
        """
        tracking_pixel = f'<img src="{base_url}/track/{tracking_id}" width="1" height="1" style="display:none;" alt="" />'
        
        # Try to insert before closing </body> tag
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', f'{tracking_pixel}</body>')
        else:
            # If no </body> tag, append to end
            html_content += tracking_pixel
        
        return html_content
    
    def get_tracking_stats(self, days=30, campaign_name=None):
        """Get tracking statistics for the last N days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        date_filter = f"AND sent_at >= datetime('now', '-{days} days')" if days else ""
        campaign_filter = f"AND campaign_name = '{campaign_name}'" if campaign_name else ""
        
        # Overall stats
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total_sent,
                COUNT(CASE WHEN opened_at IS NOT NULL THEN 1 END) as total_opened,
                ROUND(COUNT(CASE WHEN opened_at IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 2) as open_rate,
                SUM(open_count) as total_opens
            FROM email_tracking 
            WHERE 1=1 {date_filter} {campaign_filter}
        ''')
        
        result = cursor.fetchone()
        stats = {
            'total_sent': result[0] or 0,
            'total_opened': result[1] or 0,
            'open_rate': result[2] or 0.0,
            'total_opens': result[3] or 0
        }
        
        conn.close()
        return stats
    
    def get_campaign_performance(self):
        """Get performance statistics for all campaigns."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT campaign_name, total_sent, unique_opens, total_opened, open_rate
            FROM campaign_performance
            ORDER BY total_sent DESC
        ''')
        
        campaigns = []
        for row in cursor.fetchall():
            campaigns.append({
                'campaign_name': row[0],
                'total_sent': row[1],
                'unique_opens': row[2],
                'total_opened': row[3],
                'open_rate': row[4]
            })
        
        conn.close()
        return campaigns
    
    def get_email_details(self, tracking_id):
        """Get detailed information about a specific email."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get email details
        cursor.execute('''
            SELECT recipient_email, sender_email, subject, campaign_name, sent_at, 
                   opened_at, open_count, last_opened_at, user_agent, ip_address
            FROM email_tracking 
            WHERE tracking_id = ?
        ''', (tracking_id,))
        
        email_data = cursor.fetchone()
        if not email_data:
            conn.close()
            return None
        
        # Get all opens
        cursor.execute('''
            SELECT opened_at, user_agent, ip_address, referer
            FROM email_opens 
            WHERE tracking_id = ?
            ORDER BY opened_at DESC
        ''', (tracking_id,))
        
        opens = cursor.fetchall()
        
        conn.close()
        
        return {
            'tracking_id': tracking_id,
            'recipient_email': email_data[0],
            'sender_email': email_data[1],
            'subject': email_data[2],
            'campaign_name': email_data[3],
            'sent_at': email_data[4],
            'opened_at': email_data[5],
            'open_count': email_data[6],
            'last_opened_at': email_data[7],
            'user_agent': email_data[8],
            'ip_address': email_data[9],
            'opens': [{'opened_at': o[0], 'user_agent': o[1], 'ip_address': o[2], 'referer': o[3]} for o in opens]
        }

# Example usage
if __name__ == "__main__":
    # Initialize tracker
    tracker = EmailTracker()
    
    # Track a new email
    tracking_id = tracker.track_email_sent(
        recipient_email="test@example.com",
        sender_email="sender@company.com",
        subject="Welcome to our service!",
        campaign_name="Welcome Series 2024"
    )
    
    print(f"Tracking ID: {tracking_id}")
    
    # Simulate email open
    tracker.track_email_open(tracking_id, "Mozilla/5.0", "192.168.1.1")
    
    # Get stats
    stats = tracker.get_tracking_stats()
    print(f"Open Rate: {stats['open_rate']}%")
