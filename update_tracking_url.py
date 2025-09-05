"""
🔄 Update Tracking URLs
Update your email sending functions to use the public tracking URL
"""

from tracking_config import TRACKING_CONFIG

def update_email_functions():
    """Update the base_url in your email sending functions"""
    
    # Read the current file
    with open('2025_hackathon.py', 'r') as f:
        content = f.read()
    
    # Replace localhost URLs with public URL
    old_urls = [
        'base_url="http://localhost:5001"',
        'base_url="http://localhost:5000"',
        'base_url="http://127.0.0.1:5001"',
        'base_url="http://127.0.0.1:5000"'
    ]
    
    new_url = f'base_url="{TRACKING_CONFIG["BASE_URL"]}"'
    
    updated_content = content
    for old_url in old_urls:
        updated_content = updated_content.replace(old_url, new_url)
    
    # Write back to file
    with open('2025_hackathon.py', 'w') as f:
        f.write(updated_content)
    
    print(f"✅ Updated tracking URLs to: {TRACKING_CONFIG['BASE_URL']}")
    print("📧 Your emails will now use the public tracking URL")

if __name__ == '__main__':
    update_email_functions()
