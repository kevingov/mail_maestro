"""
🧪 Test Script for Email Tracking System
Run this to test your email tracking pixel implementation.
"""

from email_tracker import EmailTracker
from tracking_dashboard import app
import threading
import time
import requests

def test_email_tracking():
    """Test the complete email tracking workflow."""
    print("🧪 Testing Email Tracking System...")
    
    # Initialize tracker
    tracker = EmailTracker()
    
    # Test 1: Create tracking entries
    print("\n📧 Test 1: Creating tracked emails...")
    
    test_emails = [
        {
            'recipient': 'john@example.com',
            'subject': 'Welcome to Affirm!',
            'campaign': 'Welcome Series 2024'
        },
        {
            'recipient': 'jane@example.com', 
            'subject': 'Your Application Update',
            'campaign': 'Application Updates'
        },
        {
            'recipient': 'bob@example.com',
            'subject': 'New Features Available', 
            'campaign': 'Product Updates'
        }
    ]
    
    tracking_ids = []
    for email in test_emails:
        tracking_id = tracker.track_email_sent(
            recipient_email=email['recipient'],
            sender_email='noreply@affirm.com',
            subject=email['subject'],
            campaign_name=email['campaign']
        )
        tracking_ids.append(tracking_id)
        print(f"   ✅ Created tracking for {email['recipient']} -> {tracking_id}")
    
    # Test 2: Add tracking pixels to email content
    print("\n🎯 Test 2: Adding tracking pixels to email content...")
    
    sample_email = """
    <html>
    <body>
        <h1>Welcome to Affirm!</h1>
        <p>Thank you for joining us.</p>
        <p>Best regards,<br>The Affirm Team</p>
    </body>
    </html>
    """
    
    tracked_email = tracker.add_tracking_to_email(sample_email, tracking_ids[0])
    print(f"   ✅ Original email length: {len(sample_email)} chars")
    print(f"   ✅ Tracked email length: {len(tracked_email)} chars")
    print(f"   ✅ Tracking pixel added: {'track/' in tracked_email}")
    
    # Test 3: Simulate email opens
    print("\n📖 Test 3: Simulating email opens...")
    
    # Simulate opens for first email (multiple opens)
    tracker.track_email_open(tracking_ids[0], "Mozilla/5.0 (Chrome)", "192.168.1.100")
    tracker.track_email_open(tracking_ids[0], "Mozilla/5.0 (Safari)", "192.168.1.100")  # Second open
    
    # Simulate open for second email
    tracker.track_email_open(tracking_ids[1], "Mozilla/5.0 (Firefox)", "10.0.0.1")
    
    print(f"   ✅ Simulated opens for {len(tracking_ids)} emails")
    
    # Test 4: Check statistics
    print("\n📊 Test 4: Checking tracking statistics...")
    
    stats = tracker.get_tracking_stats()
    print(f"   📈 Total Sent: {stats['total_sent']}")
    print(f"   📈 Total Opened: {stats['total_opened']}")
    print(f"   📈 Open Rate: {stats['open_rate']}%")
    print(f"   📈 Total Opens: {stats['total_opens']}")
    
    # Test 5: Campaign performance
    print("\n🎯 Test 5: Checking campaign performance...")
    
    campaigns = tracker.get_campaign_performance()
    for campaign in campaigns:
        print(f"   📊 {campaign['campaign_name']}: {campaign['open_rate']}% open rate")
        print(f"      - Sent: {campaign['total_sent']}, Opened: {campaign['unique_opens']}")
    
    # Test 6: Email details
    print("\n🔍 Test 6: Checking email details...")
    
    details = tracker.get_email_details(tracking_ids[0])
    if details:
        print(f"   📧 Email to: {details['recipient_email']}")
        print(f"   📧 Subject: {details['subject']}")
        print(f"   📧 Campaign: {details['campaign_name']}")
        print(f"   📧 Open Count: {details['open_count']}")
        print(f"   📧 Opens: {len(details['opens'])}")
    
    print("\n✅ Email tracking tests completed successfully!")
    print("\n🚀 Next steps:")
    print("   1. Start the dashboard: python tracking_dashboard.py")
    print("   2. Visit: http://localhost:5000/dashboard")
    print("   3. Test tracking pixel: http://localhost:5000/test-tracking")
    print("   4. View stats: http://localhost:5000/tracking/stats")
    
    return tracking_ids

def test_dashboard_endpoints():
    """Test dashboard API endpoints (requires running Flask app)."""
    print("\n🌐 Testing Dashboard Endpoints...")
    
    base_url = "http://localhost:5000"
    endpoints = [
        "/tracking/stats",
        "/tracking/campaigns", 
        "/api/dashboard-data",
        "/api/charts"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=2)
            if response.status_code == 200:
                print(f"   ✅ {endpoint}: OK")
            else:
                print(f"   ❌ {endpoint}: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  {endpoint}: Not reachable (Flask app not running?)")
    
    print("   💡 Start Flask app with: python tracking_dashboard.py")

if __name__ == "__main__":
    # Run basic tracking tests
    tracking_ids = test_email_tracking()
    
    # Test dashboard endpoints (if Flask app is running)
    test_dashboard_endpoints()
    
    print(f"\n🎉 Testing complete! Sample tracking IDs: {tracking_ids[:2]}...")
