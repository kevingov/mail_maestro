"""
🔍 Debug Email Tracking - Test Your Specific Email
"""

import sqlite3
import webbrowser
from email_tracker import EmailTracker

def debug_your_email():
    """Debug the most recent email sent to you."""
    
    conn = sqlite3.connect('email_tracking.db')
    cursor = conn.cursor()
    
    # Get your recent email
    cursor.execute('''
        SELECT tracking_id, recipient_email, subject, sent_at, opened_at, open_count 
        FROM email_tracking 
        WHERE recipient_email LIKE "%kevin.gov%" OR recipient_email LIKE "%affirm.com%" 
        ORDER BY sent_at DESC LIMIT 1
    ''')
    
    email = cursor.fetchone()
    if not email:
        print("❌ No emails found for your address")
        return
    
    tracking_id, recipient, subject, sent_at, opened_at, open_count = email
    
    print("🔍 YOUR EMAIL DEBUG INFO:")
    print(f"📧 To: {recipient}")
    print(f"📧 Subject: {subject}")
    print(f"📧 Sent: {sent_at}")
    print(f"📊 Opens: {open_count}")
    print(f"📊 Last Open: {opened_at or 'Never'}")
    print(f"🔗 Tracking URL: http://localhost:5000/track/{tracking_id}")
    
    # Get all opens for this email
    cursor.execute('SELECT opened_at, user_agent, ip_address FROM email_opens WHERE tracking_id = ? ORDER BY opened_at DESC', (tracking_id,))
    opens = cursor.fetchall()
    
    if opens:
        print(f"\n📈 OPEN HISTORY ({len(opens)} opens):")
        for i, (opened_at, user_agent, ip_addr) in enumerate(opens, 1):
            print(f"  {i}. {opened_at} | {user_agent} | {ip_addr}")
    else:
        print("\n⚠️ NO OPENS DETECTED YET")
        print("This could be because:")
        print("  • Email client is blocking images")
        print("  • Email opened in plain text mode")
        print("  • Privacy protection enabled")
        print("  • Corporate firewall blocking requests")
    
    print(f"\n🧪 TEST THE TRACKING PIXEL:")
    print(f"Click this URL to simulate opening your email:")
    print(f"http://localhost:5000/track/{tracking_id}")
    
    # Auto-open the tracking URL for testing
    try:
        webbrowser.open(f"http://localhost:5000/track/{tracking_id}")
        print("✅ Opened tracking pixel in browser (should register as an open)")
    except:
        pass
    
    conn.close()

if __name__ == "__main__":
    debug_your_email()
