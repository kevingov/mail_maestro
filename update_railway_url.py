"""
🚂 Update Email Functions for Railway URL
Run this after you get your Railway deployment URL
"""

def update_for_railway(railway_url):
    """
    Update your email sending functions to use Railway URL
    """
    if not railway_url.startswith('https://'):
        print("❌ Railway URL should start with https://")
        return
    
    # Read the current file
    with open('2025_hackathon.py', 'r') as f:
        content = f.read()
    
    # Replace all localhost URLs with Railway URL
    old_urls = [
        'base_url="http://localhost:5001"',
        'base_url="http://localhost:5000"',
        'base_url="http://127.0.0.1:5001"',
        'base_url="http://127.0.0.1:5000"',
        'base_url="http://172.24.37.98:5001"'
    ]
    
    new_url = f'base_url="{railway_url}"'
    
    updated_content = content
    changes_made = 0
    
    for old_url in old_urls:
        if old_url in updated_content:
            updated_content = updated_content.replace(old_url, new_url)
            changes_made += 1
    
    if changes_made > 0:
        # Write back to file
        with open('2025_hackathon.py', 'w') as f:
            f.write(updated_content)
        
        print(f"✅ Updated {changes_made} email functions to use Railway URL")
        print(f"🌐 New tracking URL: {railway_url}")
        print("📧 Your emails will now use the Railway tracking pixel!")
    else:
        print("ℹ️ No localhost URLs found to update")

if __name__ == '__main__':
    print("🚂 Railway URL Updater")
    print("=" * 30)
    print("After deploying to Railway, you'll get a URL like:")
    print("https://your-app-name.railway.app")
    print()
    
    railway_url = input("Enter your Railway URL: ").strip()
    
    if railway_url:
        update_for_railway(railway_url)
    else:
        print("❌ No URL provided")
