"""
Configuration module for Mail Maestro
Contains all environment variables, constants, and application configuration
"""

import os

class Config:
    """Application configuration"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')

    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL')

    # OpenAI
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

    # Email Configuration
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "jake.morgan@affirm.com")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    # Gmail OAuth
    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
    GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")
    GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON")

    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
    GOOGLE_SHEETS_NAME = os.getenv("GOOGLE_SHEETS_NAME", "Send_Logs")

    # Custom Prompts
    NEW_EMAIL_PROMPT_TEMPLATE = os.getenv("NEW_EMAIL_PROMPT_TEMPLATE")
    REPLY_EMAIL_PROMPT_TEMPLATE = os.getenv("REPLY_EMAIL_PROMPT_TEMPLATE")

    # Gmail API Scopes
    GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send',
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/gmail.modify']


# Affirm Voice Guidelines
AFFIRM_VOICE_GUIDELINES = """
As an AI-powered business development assistant at Affirm, your tone must strictly follow Affirm's brand voice:

✅ **Sharp, not snarky:** Be witty, clear, and engaging, but never cynical.
✅ **Sincere, not schmaltzy:** Supportive but not overly sentimental.
✅ **To-the-point, not harsh:** Concise, clear, and direct without being blunt.
✅ **Encouraging, not irresponsible:** Promote responsible financial behavior.
✅ **No Asterisks Policy:** Avoid misleading fine print, hidden terms, or deceptive wording.

### **Example Do's & Don'ts:**
✔️ "Smarter than the average card." (Concise, informative)
❌ "Your credit card sucks." (Harsh, negative)
✔️ "See how much you can spend." (Encouraging)
❌ "You deserve to splurge." (Irresponsible tone)

Use these principles in every response.
"""

# HTML Email Template
PARDOT_EMAIL_TEMPLATE = """<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Affirm Email</title>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
        <style>

        </style>
    </head>
    <body>

        <!-- 🔹 Email Wrapper -->
        <div class="container">

            <!-- 🔹 Affirm Logo (Header) -->
            <div class="logo-container">

            </div>


            <!-- 🔹 Email Content -->
            <p style="line-height: 1.6;">{{EMAIL_CONTENT}}</p>



        </div>



    </body>
    </html>"""
