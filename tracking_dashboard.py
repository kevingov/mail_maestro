"""
📊 Email Tracking Dashboard with Flask Routes
Provides web dashboard and API endpoints for email tracking analytics.
"""

from flask import Flask, render_template, jsonify, request, send_file, Response
import json
from email_tracker import EmailTracker
import os
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)

# Initialize email tracker
tracker = EmailTracker()

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """
    Serve the tracking pixel and record email open.
    This is the core tracking endpoint that emails will call.
    """
    # Get request information
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.remote_addr
    referer = request.headers.get('Referer', '')
    
    # Record the email open
    success = tracker.track_email_open(tracking_id, user_agent, ip_address, referer)
    
    # Create and return a 1x1 transparent pixel
    pixel_data = tracker.create_tracking_pixel()
    
    return Response(
        pixel_data,
        mimetype='image/png',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

@app.route('/dashboard')
def dashboard():
    """Main tracking dashboard page."""
    return render_template('tracking_dashboard.html')

@app.route('/api/dashboard-data')
def dashboard_data():
    """API endpoint for dashboard statistics."""
    # Get query parameters
    days = request.args.get('days', 30, type=int)
    campaign = request.args.get('campaign', None)
    
    # Get overall stats
    stats = tracker.get_tracking_stats(days=days, campaign_name=campaign)
    
    # Get campaign performance
    campaigns = tracker.get_campaign_performance()
    
    # Get campaign count
    campaign_count = len(campaigns)
    
    return jsonify({
        'stats': {
            'total_sent': stats['total_sent'],
            'total_opened': stats['total_opened'],
            'open_rate': stats['open_rate'],
            'total_opens': stats['total_opens'],
            'campaign_count': campaign_count
        },
        'campaigns': campaigns
    })

@app.route('/api/charts')
def chart_data():
    """API endpoint for chart data."""
    # This could be expanded to provide daily/weekly trends
    campaigns = tracker.get_campaign_performance()
    
    # Prepare data for charts
    chart_data = {
        'campaign_names': [c['campaign_name'] for c in campaigns],
        'open_rates': [c['open_rate'] for c in campaigns],
        'total_sent': [c['total_sent'] for c in campaigns],
        'unique_opens': [c['unique_opens'] for c in campaigns]
    }
    
    return jsonify(chart_data)

@app.route('/tracking/stats')
def tracking_stats():
    """API endpoint for tracking statistics with optional filters."""
    days = request.args.get('days', 30, type=int)
    campaign = request.args.get('campaign', None)
    
    stats = tracker.get_tracking_stats(days=days, campaign_name=campaign)
    return jsonify(stats)

@app.route('/tracking/campaigns')
def campaign_performance():
    """API endpoint for campaign performance data."""
    campaigns = tracker.get_campaign_performance()
    return jsonify({'campaigns': campaigns})

@app.route('/tracking/details/<tracking_id>')
def email_details(tracking_id):
    """API endpoint for specific email tracking details."""
    details = tracker.get_email_details(tracking_id)
    if details:
        return jsonify(details)
    else:
        return jsonify({'error': 'Tracking ID not found'}), 404

@app.route('/click/<tracking_id>')
def track_click(tracking_id):
    """
    Track link clicks (optional enhancement).
    Usage: Replace links in emails with /click/<tracking_id>?url=actual_url
    """
    target_url = request.args.get('url', 'https://affirm.com')
    
    # Here you could add click tracking to database
    # For now, just redirect
    return f'''
    <script>
        window.location.href = "{target_url}";
    </script>
    <p>Redirecting to <a href="{target_url}">{target_url}</a>...</p>
    '''

@app.route('/test-tracking')
def test_tracking():
    """Test endpoint to create sample tracking data."""
    # Create some test data
    test_campaigns = [
        {'email': 'test1@example.com', 'campaign': 'Welcome Series 2024', 'subject': 'Welcome to Affirm!'},
        {'email': 'test2@example.com', 'campaign': 'Product Update', 'subject': 'New Features Available'},
        {'email': 'test3@example.com', 'campaign': 'Welcome Series 2024', 'subject': 'Getting Started Guide'},
    ]
    
    tracking_ids = []
    for test in test_campaigns:
        tracking_id = tracker.track_email_sent(
            recipient_email=test['email'],
            sender_email='noreply@affirm.com',
            subject=test['subject'],
            campaign_name=test['campaign']
        )
        tracking_ids.append(tracking_id)
        
        # Simulate some opens (for testing)
        if test['email'] == 'test1@example.com':
            tracker.track_email_open(tracking_id, 'Mozilla/5.0', '192.168.1.1')
    
    return jsonify({
        'message': 'Test data created',
        'tracking_ids': tracking_ids,
        'test_pixel_url': f'/track/{tracking_ids[0]}'
    })

# Helper function to integrate with existing email sending
def send_tracked_email(to_email, subject, html_content, campaign_name=None, sender_email=None, base_url="http://localhost:5000"):
    """
    Enhanced email sending function with tracking.
    Integrates with your existing email infrastructure.
    """
    # Track the email
    tracking_id = tracker.track_email_sent(
        recipient_email=to_email,
        sender_email=sender_email,
        subject=subject,
        campaign_name=campaign_name
    )
    
    # Add tracking pixel to email content
    tracked_html = tracker.add_tracking_to_email(html_content, tracking_id, base_url)
    
    # Here you would call your existing email sending function
    # For example: your_email_function(to_email, subject, tracked_html)
    
    return {
        'tracking_id': tracking_id,
        'html_content': tracked_html,
        'status': 'ready_to_send'
    }

if __name__ == '__main__':
    # Try different ports if 5000 is occupied (common on macOS with AirPlay)
    ports_to_try = [5001, 5002, 5003, 5000]
    
    for port in ports_to_try:
        try:
            print(f"🚀 Starting Email Tracking Dashboard on port {port}...")
            print(f"📊 Dashboard: http://localhost:{port}/dashboard")
            print(f"📧 Test tracking: http://localhost:{port}/test-tracking")
            print(f"🔍 API Stats: http://localhost:{port}/tracking/stats")
            
            app.run(debug=True, host='0.0.0.0', port=port)
            break
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"❌ Port {port} is busy, trying next port...")
                continue
            else:
                raise e
