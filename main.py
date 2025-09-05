"""
🚂 Main entry point for Railway deployment
This file tells Railway how to start the email tracking app
"""

from railway_app_minimal import app

if __name__ == '__main__':
    # This will be used if Railway runs the app directly
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
