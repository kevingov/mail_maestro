"""
�� Test Public Tracking
Test your tracking pixel from external devices
"""

from tracking_config import TRACKING_CONFIG
from email_tracker import EmailTracker
import requests

def test_public_tracking():
    """Test if the tracking server is accessible publicly"""
    
    print("🧪 Testing Public Tracking Setup")
    print("=" * 50)
    
    # Test 1: Check if server is running
    try:
        health_url = f"{TRACKING_CONFIG['BASE_URL']}/api/health"
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            print("✅ Tracking server is running and accessible")
            print(f"🌐 Server URL: {TRACKING_CONFIG['BASE_URL']}")
        else:
            print(f"❌ Server returned status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to tracking server: {e}")
        print("💡 Make sure to start the server with: python3 tracking_dashboard_public.py")
        return
    
    # Test 2: Create a test tracking ID
    try:
        tracker = EmailTracker()
        test_tracking_id = tracker.track_email_sent(
            recipient_email="test@example.com",
            sender_email="sender@example.com",
            subject="Test Email for Public Tracking",
            campaign_name="Public Test"
        )
        
        print(f"✅ Created test tracking ID: {test_tracking_id}")
        
        # Test 3: Test the tracking pixel URL
        tracking_url = f"{TRACKING_CONFIG['BASE_URL']}/track/{test_tracking_id}"
        print(f"🔗 Tracking pixel URL: {tracking_url}")
        
        # Test 4: Simulate a tracking request
        response = requests.get(tracking_url, timeout=5)
        if response.status_code == 200:
            print("✅ Tracking pixel is working correctly")
            print("📱 You can now test this URL on your phone!")
        else:
            print(f"❌ Tracking pixel returned status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error creating test tracking: {e}")
    
    print("\n📱 To test on your phone:")
    print("1. Make sure your phone is on the same WiFi network")
    print("2. Open the tracking URL in your phone's browser")
    print("3. Check the dashboard to see if the open was recorded")
    print(f"4. Dashboard URL: {TRACKING_CONFIG['BASE_URL']}/dashboard")

if __name__ == '__main__':
    test_public_tracking()
