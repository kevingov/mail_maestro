"""
🚂 Railway Email Tracking App with PostgreSQL
Complete email tracking system with send and open tracking
"""

import os
import psycopg2
from flask import Flask, Response, request, jsonify
import logging
from io import BytesIO
from PIL import Image
import uuid
import datetime
import base64
import email
import pickle
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Gmail and Google API imports
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# OpenAI import
from openai import OpenAI

# Google Sheets import
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log Google Sheets availability
if not GSPREAD_AVAILABLE:
    logger.warning("gspread not available - Google Sheets integration disabled")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Email configuration (same as 2025_hackathon.py)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "jake.morgan@affirm.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Affirm Voice Guidelines (same as 2025_hackathon.py)
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

# HTML Email Template (same as 2025_hackathon.py)
pardot_email_template = """<!DOCTYPE html>
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

def format_pardot_email(first_name, email_content, recipient_email, sender_name):
    """
    Inserts dynamic data into the Pardot email template.
    Ensures email content is formatted correctly with line breaks.
    """
    formatted_email = email_content.replace("\n", "<br>")  # ✅ Convert newlines to <br> for HTML

    return pardot_email_template.replace("{{FIRST_NAME}}", first_name) \
                                .replace("{{EMAIL_CONTENT}}", formatted_email) \
                                .replace("{{SENDER_NAME}}", sender_name) \
                                .replace("{{RECIPIENT_EMAIL}}", recipient_email) \
                                .replace("{{UNSUBSCRIBE_LINK}}", "https://www.affirm.com/unsubscribe")

# Global database connection status
DB_AVAILABLE = False

def get_db_connection():
    """Get PostgreSQL connection from Railway environment variables."""
    global DB_AVAILABLE
    try:
        # Railway provides DATABASE_URL environment variable
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.warning("DATABASE_URL not found - running without database")
            DB_AVAILABLE = False
            return None
        
        conn = psycopg2.connect(database_url)
        DB_AVAILABLE = True
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        DB_AVAILABLE = False
        return None

def init_database():
    """Initialize PostgreSQL database tables."""
    global DB_AVAILABLE
    try:
        conn = get_db_connection()
        if not conn:
            logger.warning("No database connection - running in memory mode")
            DB_AVAILABLE = False
            return
        
        cursor = conn.cursor()
        
        # Email tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_tracking (
                id SERIAL PRIMARY KEY,
                tracking_id VARCHAR(255) UNIQUE NOT NULL,
                recipient_email VARCHAR(255) NOT NULL,
                sender_email VARCHAR(255),
                subject TEXT,
                campaign_name VARCHAR(255),
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                open_count INTEGER DEFAULT 0,
                last_opened_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Email opens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_opens (
                id SERIAL PRIMARY KEY,
                tracking_id VARCHAR(255) NOT NULL,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                ip_address VARCHAR(45),
                referer TEXT,
                FOREIGN KEY (tracking_id) REFERENCES email_tracking (tracking_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ PostgreSQL database initialized")
        DB_AVAILABLE = True
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        DB_AVAILABLE = False

# Initialize database on startup
init_database()

# Gmail API configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']

def authenticate_gmail():
    """Authenticate with Gmail API using environment variables or stored credentials."""
    creds = None
    
    # Method 1: Try OAuth2 credentials from environment variables (for Railway)
    client_id = os.environ.get('GMAIL_CLIENT_ID')
    client_secret = os.environ.get('GMAIL_CLIENT_SECRET') 
    refresh_token = os.environ.get('GMAIL_REFRESH_TOKEN')
    
    if client_id and client_secret and refresh_token:
        from google.oauth2.credentials import Credentials
        
        try:
            creds = Credentials(
                token=None,  # Will be refreshed
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
            # Refresh the token
            creds.refresh(Request())
            logger.info("Using Gmail OAuth2 credentials from environment variables")
            return creds
        except Exception as e:
            logger.warning(f"Failed to use OAuth2 credentials from environment: {e}")
    
    # Method 2: Try JSON credentials from environment variable
    gmail_creds_json = os.environ.get('GMAIL_CREDENTIALS_JSON')
    if gmail_creds_json:
        import json
        from google.oauth2.credentials import Credentials
        
        try:
            creds_data = json.loads(gmail_creds_json)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            logger.info("Using Gmail credentials from GMAIL_CREDENTIALS_JSON environment variable")
            return creds
        except Exception as e:
            logger.warning(f"Failed to load credentials from GMAIL_CREDENTIALS_JSON: {e}")
    
    # Method 3: Fallback to file-based authentication (for local development)
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Try multiple credential file names
            credential_files = [
                'credentials_jake_morgan.json',
                'credentials_kevin_uncommonestate.json', 
                'credentials.json'
            ]
            
            credential_file = None
            for file in credential_files:
                if os.path.exists(file):
                    credential_file = file
                    break
            
            if credential_file:
                flow = InstalledAppFlow.from_client_secrets_file(credential_file, SCOPES)
                creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            else:
                raise FileNotFoundError("Gmail credentials not found. Please set Gmail environment variables (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN) or provide a credentials file.")
    
    return creds

def extract_email_body(payload):
    """Extract the body of an email, handling both plain text and HTML."""
    body = ""

    # Case 1: If the email has multiple parts (HTML, plain text, etc.)
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part['mimeType']
            body_data = part.get('body', {}).get('data')

            if body_data:
                decoded_body = base64.urlsafe_b64decode(body_data).decode("utf-8")

                # Prefer plain text over HTML
                if mime_type == 'text/plain':
                    return decoded_body  # Return first plain text body found
                elif mime_type == 'text/html':
                    body = decoded_body  # Store HTML if no plain text is found

    # Case 2: If the email is a single part (plain text or HTML)
    else:
        body_data = payload.get('body', {}).get('data')
        if body_data:
            body = base64.urlsafe_b64decode(body_data).decode("utf-8")

    return body

def get_original_message_id(gmail_message_id):
    """
    Get the actual Message-ID header from the original Gmail message.
    This is needed for proper email threading.
    """
    try:
        creds = authenticate_gmail()
        service = build('gmail', 'v1', credentials=creds)
        
        # Get the message data
        message_data = service.users().messages().get(userId='me', id=gmail_message_id).execute()
        headers = message_data['payload']['headers']
        
        # Find the Message-ID header
        message_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), None)
        
        if message_id:
            logger.info(f"📧 Found original Message-ID: {message_id}")
            return message_id
        else:
            logger.info(f"⚠️ No Message-ID found in original email, using Gmail ID: {gmail_message_id}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error getting original Message-ID: {e}")
        return None

def has_been_replied_to(email_id, service):
    """Check if the LATEST message in the thread is from us (Jake Morgan)."""
    try:
        # Get the thread ID for this email
        email_data = service.users().messages().get(userId='me', id=email_id).execute()
        thread_id = email_data.get('threadId')
        
        if not thread_id:
            return False
            
        # Get all messages in the thread
        thread_data = service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread_data.get('messages', [])
        
        if not messages:
            return False
            
        # Get the latest message (last in the array)
        latest_message = messages[-1]
        latest_msg_data = service.users().messages().get(userId='me', id=latest_message['id']).execute()
        headers = latest_msg_data['payload']['headers']
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        
        # Check if the latest message is from us
        is_from_us = 'jake.morgan@affirm.com' in sender.lower()
        
        return is_from_us
        
    except Exception as e:
        logger.error(f"Error checking reply status for email {email_id}: {e}")
        return False

def generate_ai_response(email_body, sender_name, recipient_name, conversation_history=None):
    """
    Generates an AI response using the same detailed prompt as generate_message.
    Creates a professional, Affirm-branded email response with full conversation context.
    """
    
    # Build conversation context if provided
    conversation_context = ""
    if conversation_history:
        conversation_context = f"""
    **Full Conversation History:**
    {conversation_history}
    
    **Latest Message to Respond To:**
    {email_body}
    """
    else:
        conversation_context = f"""
    **Latest Message to Respond To:**
    {email_body}
    """

    prompt = f"""
    {AFFIRM_VOICE_GUIDELINES}

    **TASK:** Generate a professional Affirm-branded email response to {recipient_name} from {sender_name}.

    **CONVERSATION CONTEXT:**
    {conversation_context}

    **CRITICAL RULES:**
    1. **Answer direct questions in the FIRST line** (e.g., "Are you a bot?" → "I'm an AI assistant helping with business development, but I'm here to provide real value and connect you with our human team.")
    2. **Be truthful** - don't make up information
    3. **Reference conversation history** to show you've read it
    4. **Be conversational and helpful** - acknowledge concerns before solutions
    5. **Keep under 150 words** and feel natural, not automated
    

    **OUTPUT FORMAT:**
    - **Subject Line:** [Concise subject]
    - **Email Body:** [Your response]

    For technical support, refer to customercare@affirm.com.
    """

    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        if response and response.choices:
            response_text = response.choices[0].message.content.strip()

            # Extract Subject Line and Email Body using regex (same as generate_message)
            subject_line_match = re.search(r"\*\*Subject Line:\*\*\s*(.*)", response_text)
            email_body_match = re.search(r"\*\*Email Body:\*\*\s*(.*)", response_text, re.DOTALL)

            subject_line = subject_line_match.group(1).strip() if subject_line_match else f"Re: Your Message"
            email_body = email_body_match.group(1).strip() if email_body_match else f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"

            return format_pardot_email(first_name=recipient_name, 
                                       email_content=email_body, 
                                       recipient_email="recipient@email.com", 
                                       sender_name=sender_name)

        else:
            fallback_response = f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"
            return format_pardot_email(first_name=recipient_name, 
                                       email_content=fallback_response, 
                                       recipient_email="recipient@email.com", 
                                       sender_name=sender_name)
        
    except Exception as e:
        logger.error(f"❌ Error generating AI response: {e}")
        fallback_response = f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"
        return format_pardot_email(first_name=recipient_name, 
                                   email_content=fallback_response, 
                                   recipient_email="recipient@email.com", 
                                   sender_name=sender_name)

def generate_message(merchant_name, last_activity, merchant_industry, merchant_website, sender_name, account_description="", account_revenue=0, account_employees=0, account_location="", contact_title="", account_gmv=0):
    """
    Creates an Affirm-branded outreach email using AI with detailed Salesforce data.
    Exact copy from 2025_hackathon.py.
    """
    # Handle None values and format them properly
    account_revenue_str = f"${account_revenue:,}" if account_revenue and account_revenue > 0 else "Not specified"
    account_employees_str = f"{account_employees:,}" if account_employees and account_employees > 0 else "Not specified"
    account_gmv_str = f"${account_gmv:,.2f}" if account_gmv and account_gmv > 0 else "Not available"
    account_description_str = account_description if account_description else "Not provided"
    account_location_str = account_location if account_location else "Not specified"
    contact_title_str = contact_title if contact_title else "Not specified"
    merchant_industry_str = merchant_industry if merchant_industry else "Business"
    merchant_website_str = merchant_website if merchant_website else "Not provided"
    
    prompt = f"""
    {AFFIRM_VOICE_GUIDELINES}
    
    Generate a **professional, Affirm-branded business email** to re-engage {merchant_name}, a merchant in the {merchant_industry_str} industry, who has completed technical integration with Affirm but has **not yet launched**. The goal is to encourage them to go live — without offering a meeting or call.

    **Context:**
    - Contact Name: {merchant_name}
    - Contact Title: {contact_title_str}
    - Industry: {merchant_industry_str}
    - Website: {merchant_website_str}
    - Sender: {sender_name}
    - Status: Integrated with Affirm, not yet live
    - Account Description: {account_description_str}
    - Annual Revenue: {account_revenue_str}
    - Trailing 12M GMV: {account_gmv_str}
    - Employees: {account_employees_str}
    - Location: {account_location_str}

    **Tone & Style Guidelines:**
    - Use Affirm's brand voice: smart, approachable, efficient
    - Do **not** offer a call or meeting
    - Make it feel like a 1:1 business development check-in
    - Be helpful, not pushy
    - Reference their specific industry and business context

    **Spam Avoidance Rules:**
    - No excessive punctuation or all-caps
    - Avoid trigger words like "FREE," "ACT NOW," or "LIMITED TIME"
    - Avoid heavy use of numbers or dollar signs

    **Include in the Email:**
    - **Subject Line**: Under 50 characters, straightforward and relevant
    - **Opening Line**: Greet the merchant by name and acknowledge that integration is complete
    - **Body**: 
        - Reiterate the value of Affirm to their specific industry or customer base
        - Reference their business context (size, industry, etc.) if relevant
        - Encourage them to take the final step to go live
        - Offer light-touch support or resources (but **not** a meeting)
    - **CTA**: Prompt action, but keep it casual and async — e.g., "Let us know when you're ready," or "We're here if you need anything."

    **Output Format:**
    - **Subject Line:** [Concise subject line]
    - **Email Body:** [Email message]

    Keep the email under 130 words. Make it feel natural and human, not like marketing automation.
    """

    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        if response and response.choices:
            response_text = response.choices[0].message.content.strip()

            # Extract Subject Line and Email Body using regex
            subject_line_match = re.search(r"\*\*Subject Line:\*\*\s*(.*)", response_text)
            email_body_match = re.search(r"\*\*Email Body:\*\*\s*(.*)", response_text, re.DOTALL)

            subject_line = subject_line_match.group(1).strip() if subject_line_match else f"Hi {merchant_name}, Let's Connect!"
            email_body = email_body_match.group(1).strip() if email_body_match else "Let's connect to discuss how Affirm can benefit your business."

            return subject_line, email_body

        else:
            return f"Hi {merchant_name}, Let's Connect!", "Let's connect to discuss how Affirm can benefit your business."

        
    except Exception as e:
        logger.error(f"❌ Error generating AI response: {e}")
        return f"Hi {merchant_name}, Let's Connect!", "Let's connect to discuss how Affirm can benefit your business."

def send_email(to_email, merchant_name, subject_line, email_content, campaign_name=None, base_url="https://web-production-6dfbd.up.railway.app"):
    """Send email with tracking - exact copy from 2025_hackathon.py."""
    try:
        from email_tracker import EmailTracker
        import time
        import random
        
        # Initialize email tracker
        tracker = EmailTracker()
        
        # Track the email and get tracking ID
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com'),
            subject=subject_line,
            campaign_name=campaign_name or "Personalized Outreach"
        )
        
        # Add tracking pixel to email content
        tracked_email_content = tracker.add_tracking_to_email(email_content, tracking_id, base_url)
        
        # Create email message with enhanced headers
        msg = MIMEMultipart()
        msg["From"] = f"Jake Morgan - Affirm <{os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')}>"
        msg["To"] = to_email
        msg["Subject"] = subject_line
        msg["Reply-To"] = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')
        msg["Return-Path"] = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')
        msg["Message-ID"] = f"<{tracking_id}@affirm.com>"
        msg["X-Mailer"] = "Affirm Business Development"
        msg["X-Priority"] = "3"
        msg["X-MSMail-Priority"] = "Normal"
        msg["Importance"] = "Normal"
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@affirm.com?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["X-Affirm-Campaign"] = campaign_name or "Personalized Outreach"
        msg["X-Affirm-Source"] = "Business Development"
        
        # Create HTML part
        html_part = MIMEText(tracked_email_content, 'html')
        msg.attach(html_part)
        
        # Add random delay
        delay = random.uniform(2, 5)
        logger.info(f"⏱️ Waiting {delay:.1f} seconds before sending...")
        time.sleep(delay)
        
        # Send email via Gmail API (Railway network can't reach SMTP)
        try:
            creds = authenticate_gmail()
            service = build('gmail', 'v1', credentials=creds)
            
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            message_body = {'raw': raw_message}
            
            response = service.users().messages().send(userId='me', body=message_body).execute()
            logger.info("📧 Email sent successfully via Gmail API!")
            logger.info(f"📧 Gmail Message ID: {response.get('id')}")
            logger.info(f"📧 Thread ID: {response.get('threadId')}")
            logger.info(f"📧 Label IDs: {response.get('labelIds')}")
            
        except Exception as gmail_error:
            logger.error(f"❌ Gmail API Error: {gmail_error}")
            raise gmail_error
        
        logger.info("📧 EMAIL SENT SUCCESSFULLY!")
        logger.info(f"📧 To: {to_email}")
        logger.info(f"📧 Subject: {subject_line}")
        logger.info(f"📧 Tracking ID: {tracking_id}")
        
        return {
            'status': 'success',
            'tracking_id': tracking_id,
            'tracking_url': f"{base_url}/track/{tracking_id}",
            'message_id': response.get('id'),
            'thread_id': response.get('threadId')
        }
        
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

def send_threaded_email_reply(to_email, subject, reply_content, original_message_id, sender_name):
    """
    Send a threaded email reply that maintains the conversation thread.
    Uses SMTP like 2025_hackathon.py for better outbox visibility.
    """
    try:
        import smtplib
        import time
        import random
        from email_tracker import EmailTracker
        
        logger.info(f"Preparing to send threaded reply to {to_email} with subject: {subject}")
        
        # Initialize email tracker (same as 2025_hackathon.py)
        tracker = EmailTracker()
        
        # Track the email and get tracking ID
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com'),
            subject=subject,
            campaign_name="AI Email Reply"
        )
        
        # Add tracking pixel to email content
        tracked_email_content = tracker.add_tracking_to_email(reply_content, tracking_id, "https://web-production-6dfbd.up.railway.app")
        
        # Create email message with enhanced headers (same as 2025_hackathon.py)
        msg = MIMEMultipart()
        msg["From"] = f"Jake Morgan - Affirm <{os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')}>"
        msg["To"] = to_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith('Re:') else subject
        msg["Reply-To"] = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')
        msg["Return-Path"] = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')
        msg["Message-ID"] = f"<{tracking_id}@affirm.com>"
        msg["X-Mailer"] = "Affirm Business Development"
        msg["X-Priority"] = "3"
        msg["X-MSMail-Priority"] = "Normal"
        msg["Importance"] = "Normal"
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@affirm.com?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["X-Affirm-Campaign"] = "AI Email Reply"
        msg["X-Affirm-Source"] = "Business Development"
        
        # Add proper threading headers using the actual Message-ID (same as 2025_hackathon.py)
        original_message_id_header = get_original_message_id(original_message_id)
        if original_message_id_header:
            msg['In-Reply-To'] = original_message_id_header
            msg['References'] = original_message_id_header
        else:
            # Fallback to Gmail message ID if we can't get the original Message-ID
            msg['In-Reply-To'] = f"<{original_message_id}@gmail.com>"
            msg['References'] = f"<{original_message_id}@gmail.com>"
        
        # Create HTML part
        html_part = MIMEText(tracked_email_content, 'html')
        msg.attach(html_part)
        
        # Add random delay (same as 2025_hackathon.py)
        delay = random.uniform(2, 5)
        logger.info(f"⏱️ Waiting {delay:.1f} seconds before sending...")
        time.sleep(delay)
        
        # Send email via Gmail API with proper threading
        try:
            creds = authenticate_gmail()
            service = build('gmail', 'v1', credentials=creds)
            
            # Get the original message to extract thread ID for proper threading
            try:
                original_message = service.users().messages().get(userId='me', id=original_message_id).execute()
                thread_id = original_message.get('threadId')
                logger.info(f"📧 Found original thread ID: {thread_id}")
            except Exception as e:
                logger.warning(f"⚠️ Could not get original thread ID: {e}")
                thread_id = None
            
            # Create message for Gmail API with proper threading
            message = MIMEMultipart()
            message["to"] = to_email
            message["subject"] = subject
            message["from"] = "jake.morgan@affirm.com"
            
            # Add threading headers for proper conversation threading
            if original_message_id:
                original_message_id_header = get_original_message_id(original_message_id)
                if original_message_id_header:
                    message['In-Reply-To'] = original_message_id_header
                    message['References'] = original_message_id_header
                    logger.info(f"📧 Using original Message-ID: {original_message_id_header}")
                else:
                    message['In-Reply-To'] = f"<{original_message_id}@gmail.com>"
                    message['References'] = f"<{original_message_id}@gmail.com>"
                    logger.info(f"📧 Using Gmail message ID: {original_message_id}")
            
            message.attach(MIMEText(tracked_email_content, "html"))
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            
            # Use threadId in the message body for proper threading
            message_body = {'raw': raw_message}
            if thread_id:
                message_body['threadId'] = thread_id
                logger.info(f"📧 Sending to existing thread: {thread_id}")
            
            logger.info(f"📧 Sending email to: {to_email}")
            logger.info(f"📧 Subject: {subject}")
            logger.info(f"📧 Message size: {len(raw_message)} characters")
            
            response = service.users().messages().send(userId='me', body=message_body).execute()
            logger.info("📧 Email sent successfully via Gmail API!")
            logger.info(f"📧 Gmail Message ID: {response.get('id')}")
            logger.info(f"📧 Thread ID: {response.get('threadId')}")
            logger.info(f"📧 Label IDs: {response.get('labelIds')}")
            
        except Exception as gmail_error:
            logger.error(f"❌ Gmail API Error: {gmail_error}")
            raise gmail_error
        
        logger.info("📧 EMAIL SENT SUCCESSFULLY!")
        logger.info(f"📧 To: {to_email}")
        logger.info(f"📧 Subject: {subject}")
        logger.info(f"📧 Tracking ID: {tracking_id}")
        
        return {
            'status': f"Reply sent to {to_email}",
            'tracking_id': tracking_id,
            'tracking_url': f"https://web-production-6dfbd.up.railway.app/tracking/details/{tracking_id}"
        }
        
    except Exception as e:
        logger.error(f"Error sending threaded email reply: {e}")
        raise e

def reply_to_emails_with_accounts(accounts):
    """Process emails for specific accounts provided by Workato - exact copy from 2025_hackathon.py."""
    emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
    responses = []

    logger.info(f"🔍 Processing {len(emails_needing_replies)} threads individually...")
    
    # Process each thread individually (don't group by sender)
    for i, email in enumerate(emails_needing_replies):
        thread_id = email.get('threadId', 'No ID')
        logger.info(f"📧 Processing thread {i+1}/{len(emails_needing_replies)}: {thread_id}")
        
        # Extract contact information
        contact_name = email.get('contact_name', email['sender'].split("@")[0].capitalize())
        contact_email = email['sender']
        account_id = email.get('account_id')
        salesforce_id = email.get('salesforce_id')
        
        # Sender information (matching send_new_email)
        sender_name = "Jake Morgan"
        sender_title = "Business Development"
        
        # For single email, use it as the conversation context
        conversation_content = f"📧 EMAIL TO RESPOND TO:\nSubject: {email['subject']}\nFrom: {email['sender']}\nBody: {email['body']}"
        
        try:
            # Generate AI response using the email content
            ai_response = generate_ai_response(email['body'], sender_name, contact_name, conversation_content)
            
            # Send threaded reply
            email_result = send_threaded_email_reply(
                to_email=contact_email,
                subject=email['subject'],
                reply_content=ai_response,
                original_message_id=email['id'],
                sender_name=sender_name
            )
            
            email_status = email_result['status'] if isinstance(email_result, dict) else email_result
            tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""
            
            # Salesforce logging removed
            
            logger.info(f"✅ Sent reply to thread {thread_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing email from {contact_email}: {e}")
            email_status = "❌ Failed to process email"
            email_result = None
            tracking_info = ""
            ai_response = "<p>Sorry, I couldn't generate a response at this time.</p>"

        # Mark email as read (skip for now - function not implemented)
        # try:
        #     mark_emails_as_read([email['id']])
        # except Exception as e:
        #     logger.error(f"❌ Error marking email as read: {e}")

        responses.append({
            "sender": contact_email,
            "contact_name": contact_name,
            "account_id": account_id,
            "salesforce_id": salesforce_id,
            "thread_id": thread_id,
            "subject": email['subject'],
            "original_message": conversation_content,
            "ai_response": ai_response,
            "email_status": email_status + tracking_info,
            "tracking_id": email_result.get('tracking_id') if isinstance(email_result, dict) else None,
            "tracking_url": email_result.get('tracking_url') if isinstance(email_result, dict) else None,
            "emails_processed": 1
        })

    logger.info(f"📊 Processed {len(responses)} conversation threads")
    return {
        "status": "success",
        "message": f"Processed {len(responses)} conversation threads",
        "emails_processed": len(responses),
        "responses": responses
    }

def get_emails_needing_replies_with_accounts(accounts):
    """Get emails needing replies using accounts provided by Workato instead of Salesforce query."""
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    logger.info("Connected to Gmail API")

    # Create a lookup dictionary for email addresses from Workato accounts
    account_emails = {}
    for account in accounts:
        email_addr = account.get('email', '').lower()
        if email_addr:
            account_emails[email_addr] = {
                'contact_id': account.get('contact_id'),
                'account_id': account.get('account_id'),
                'contact_name': account.get('name')
            }

    logger.info(f"Processing {len(account_emails)} email addresses from Workato")

    # Fetch ALL emails from inbox (not just unread)
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=100).execute()
    messages = results.get('messages', [])
    if not messages:
        logger.warning("No emails found in inbox!")
        return []

    logger.info(f"Found {len(messages)} total emails in inbox")

    emails = []
    for msg in messages:
        msg_id = msg['id']
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        
        # Extract email details
        headers = message['payload'].get('headers', [])
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
        message_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), '')
        thread_id = message.get('threadId')
        
        # Extract sender email address
        sender_email = sender
        if '<' in sender and '>' in sender:
            sender_email = sender.split('<')[1].split('>')[0]
        sender_email = sender_email.lower()
        
        # Check if this email is from one of the Workato-provided accounts
        if sender_email in account_emails:
            # Get email body
            body = extract_email_body(message['payload'])
            
            # Add account information from Workato
            account_info = account_emails[sender_email]
            
            email_data = {
                'id': msg_id,
                'threadId': thread_id,
                'sender': sender,
                'subject': subject,
                'body': body,
                'date': date,
                'message_id': message_id,
                'contact_name': account_info['contact_name'],
                'account_id': account_info['account_id'],
                'contact_id': account_info['contact_id']
            }
            emails.append(email_data)
            logger.info(f"Found email from Workato account: {sender} - {subject}")

    logger.info(f"Found {len(emails)} emails from Workato-provided accounts")

    # Group emails by conversation thread (threadId)
    thread_emails = {}
    for email in emails:
        thread_id = email.get('threadId')
        if thread_id:
            if thread_id not in thread_emails:
                thread_emails[thread_id] = []
            thread_emails[thread_id].append(email)
    
    emails_needing_replies = []
    
    # Check each conversation thread - only reply if last message is from merchant
    for thread_id, emails_in_thread in thread_emails.items():
        # Sort emails by date to get the latest one
        emails_in_thread.sort(key=lambda x: x.get('date', ''), reverse=True)
        latest_email = emails_in_thread[0]  # Most recent email in this thread
        
        # Check if the latest message is from the merchant (not from us)
        latest_sender = latest_email.get('sender', '').lower()
        is_from_merchant = False
        
        # Check if latest sender is one of our Workato accounts (merchant)
        for account_email in account_emails.keys():
            if account_email in latest_sender:
                is_from_merchant = True
                break
        
        # Only reply if:
        # 1. Latest message is from merchant (not from us)
        # 2. Thread hasn't been replied to yet
        if is_from_merchant and not has_been_replied_to(latest_email['id'], service):
            emails_needing_replies.append(latest_email)
            logger.info(f"Conversation thread {thread_id} from {latest_email['sender']} needs a reply (last message from merchant)")
        else:
            if not is_from_merchant:
                logger.info(f"Conversation thread {thread_id} - latest message is from us, skipping reply")
            else:
                logger.info(f"Conversation thread {thread_id} from {latest_email['sender']} already has a reply")

    logger.info(f"Found {len(emails_needing_replies)} conversation threads needing replies")
    return emails_needing_replies

@app.route('/')
def home():
    """Home page with service info."""
    db_status = "PostgreSQL (connected)" if DB_AVAILABLE else "Memory mode (no persistence)"
    return jsonify({
        'service': 'Email Tracking System with Workato Integration',
        'status': 'running',
        'version': '2.0.0',
        'database': db_status,
        'endpoints': {
            'track_email_send': 'POST /api/track-send',
            'tracking_pixel': 'GET /track/<tracking_id>',
            'health_check': 'GET /api/health',
            'tracking_stats': 'GET /api/stats',
            'workato_reply_emails': 'POST /api/workato/reply-to-emails',
            'workato_reply_status': 'POST /api/workato/reply-to-emails/status',
            'workato_send_new_email': 'POST /api/workato/send-new-email',
            'workato_check_email_sent': 'POST /api/workato/check-email-sent',
            'workato_get_all_emails': 'GET/POST /api/workato/get-all-emails'
        }
    })

@app.route('/api/track-send', methods=['POST'])
def track_email_send():
    """API endpoint to track email sends."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'error': 'Database not available',
                'message': 'PostgreSQL database is not connected'
            }), 503
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Extract required fields
        recipient_email = data.get('recipient_email')
        sender_email = data.get('sender_email')
        subject = data.get('subject')
        campaign_name = data.get('campaign_name')
        
        if not recipient_email:
            return jsonify({'error': 'recipient_email is required'}), 400
        
        # Generate tracking ID
        tracking_id = str(uuid.uuid4())
        
        # Store in database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
            VALUES (%s, %s, %s, %s, %s)
        ''', (tracking_id, recipient_email, sender_email, subject, campaign_name))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📧 Email send tracked: {tracking_id} -> {recipient_email}")
        
        return jsonify({
            'status': 'success',
            'tracking_id': tracking_id,
            'tracking_url': f"https://web-production-6dfbd.up.railway.app/track/{tracking_id}",
            'message': f'Email send tracked for {recipient_email}'
        })
        
    except Exception as e:
        logger.error(f"❌ Error tracking email send: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """Serve tracking pixel and log the request to PostgreSQL with 30-second delay filtering only."""
    try:
        # Log the tracking request
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.remote_addr
        referer = request.headers.get('Referer', '')
        
        # Simple filtering - only filter opens within 30 seconds of sending
        is_false_open = False
        false_open_reasons = []
        
        # Try to track in database if available
        if DB_AVAILABLE:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    
                    # Check if tracking_id exists in email_tracking table
                    cursor.execute('SELECT tracking_id, sent_at FROM email_tracking WHERE tracking_id = %s', (tracking_id,))
                    email_record = cursor.fetchone()
                    
                    if not email_record:
                        logger.warning(f"Tracking ID {tracking_id} not found in email_tracking table")
                        # Create a placeholder record
                        cursor.execute('''
                            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (tracking_id) DO NOTHING
                        ''', (tracking_id, 'unknown@example.com', 'unknown@example.com', 'Unknown', 'Unknown'))
                        conn.commit()
                    
                        # Get the sent_at time for the new record
                        cursor.execute('SELECT tracking_id, sent_at FROM email_tracking WHERE tracking_id = %s', (tracking_id,))
                        email_record = cursor.fetchone()
                    
                    # Check for instant opens (within 30 seconds of sending)
                    if email_record:
                        sent_at = email_record[1]  # sent_at timestamp
                        
                        from datetime import datetime
                        current_time = datetime.now()
                        
                        # Handle timezone-aware datetime comparison
                        if sent_at.tzinfo is None:
                            # If sent_at is naive, assume UTC
                            sent_at = sent_at.replace(tzinfo=None)
                            current_time = current_time.replace(tzinfo=None)
                        
                        time_diff = (current_time - sent_at).total_seconds()
                        
                        # Filter out instant opens (30 seconds or less)
                        if time_diff < 30:
                            is_false_open = True
                            false_open_reasons.append(f"Instant open: {time_diff:.1f}s after send")
                    
                    # Always insert the open record (for debugging)
                    cursor.execute('''
                        INSERT INTO email_opens (tracking_id, user_agent, ip_address, referer)
                        VALUES (%s, %s, %s, %s)
                    ''', (tracking_id, user_agent, ip_address, referer))
                    
                    # Only update open count if it's not a false open
                    if not is_false_open:
                    # Update open count
                        cursor.execute('''
                            UPDATE email_tracking 
                            SET open_count = open_count + 1, last_opened_at = CURRENT_TIMESTAMP
                            WHERE tracking_id = %s
                        ''', (tracking_id,))
                        
                        conn.commit()
                        logger.info(f"✅ Real email opened! Tracking ID: {tracking_id}")
                    else:
                        conn.commit()
                        logger.info(f"🤖 False open filtered: {tracking_id} - {'; '.join(false_open_reasons)}")
                        
                        conn.close()
                except Exception as db_error:
                    logger.error(f"Database error: {db_error}")
                    if conn:
                        conn.close()
                    logger.info(f"📧 Email opened! Tracking ID: {tracking_id} (DB error, logged to console)")
        else:
            if not is_false_open:
                logger.info(f"📧 Email opened! Tracking ID: {tracking_id} (no DB)")
            else:
                logger.info(f"🤖 False open filtered: {tracking_id} - {'; '.join(false_open_reasons)} (no DB)")
        
        # Log details
        if not is_false_open:
            logger.info(f"🌐 IP: {ip_address}")
            logger.info(f" User Agent: {user_agent}")
        else:
            logger.info(f"🤖 Filtered - IP: {ip_address}")
            logger.info(f"🤖 Filtered - User Agent: {user_agent}")
        
        # Create and return the pixel
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        
        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    except Exception as e:
        logger.error(f"❌ Error tracking email open: {e}")
        # Return a simple pixel even if tracking fails
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_io = BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)
        
        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    if DB_AVAILABLE:
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.close()
                return jsonify({
                    'status': 'healthy',
                    'service': 'Email Tracking System',
                    'version': '1.0.0',
                    'database': 'PostgreSQL connected'
                })
        except Exception as e:
            return jsonify({
                'status': 'healthy',
                'service': 'Email Tracking System',
                'version': '1.0.0',
                'database': f'PostgreSQL error: {str(e)}'
            })
    
    return jsonify({
        'status': 'healthy',
        'service': 'Email Tracking System',
        'version': '1.0.0',
        'database': 'Memory mode (no persistence)'
    })

@app.route('/api/workato/get-all-emails', methods=['POST', 'GET'])
def workato_get_all_emails():
    """
    Workato endpoint to get all email tracking records.
    Supports both GET and POST requests.
    
    Optional query parameters (GET) or body (POST):
    {
        "limit": 100,           # Max number of records (default: 1000)
        "offset": 0,            # Pagination offset (default: 0)
        "order_by": "sent_at",  # Field to order by (default: "sent_at")
        "order_direction": "DESC",  # ASC or DESC (default: "DESC")
        "campaign_name": "Workato Personalized Outreach",  # Filter by campaign
        "recipient_email": "contact@example.com"  # Filter by recipient
    }
    
    Returns:
    {
        "status": "success",
        "total_count": 150,
        "returned_count": 100,
        "offset": 0,
        "limit": 100,
        "emails": [...]
    }
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'error': 'Database not available',
                'message': 'PostgreSQL database is not connected'
            }), 503
        
        # Support both GET and POST
        if request.method == 'GET':
            data = request.args.to_dict()
            # Convert string numbers to int
            if 'limit' in data:
                try:
                    data['limit'] = int(data['limit'])
                except (ValueError, TypeError):
                    data['limit'] = 1000
            if 'offset' in data:
                try:
                    data['offset'] = int(data['offset'])
                except (ValueError, TypeError):
                    data['offset'] = 0
        else:
            data = request.get_json() if request.is_json else {}
        
        # Set defaults
        limit = min(int(data.get('limit', 1000)), 10000)  # Max 10,000 records
        offset = int(data.get('offset', 0))
        order_by = data.get('order_by', 'sent_at')
        order_direction = data.get('order_direction', 'DESC').upper()
        campaign_filter = data.get('campaign_name', '')
        recipient_filter = data.get('recipient_email', '').lower()
        
        # Validate order_by field (prevent SQL injection)
        allowed_order_fields = ['sent_at', 'created_at', 'recipient_email', 'subject', 'campaign_name', 'open_count']
        if order_by not in allowed_order_fields:
            order_by = 'sent_at'
        
        # Validate order direction
        if order_direction not in ['ASC', 'DESC']:
            order_direction = 'DESC'
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        cursor = conn.cursor()
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if campaign_filter:
            where_conditions.append("campaign_name = %s")
            params.append(campaign_filter)
        
        if recipient_filter:
            where_conditions.append("LOWER(recipient_email) = %s")
            params.append(recipient_filter)
        
        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM email_tracking{where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Get records
        query = f"""
            SELECT 
                id,
                tracking_id,
                recipient_email,
                sender_email,
                subject,
                campaign_name,
                sent_at,
                open_count,
                last_opened_at,
                created_at
            FROM email_tracking
            {where_clause}
            ORDER BY {order_by} {order_direction}
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        cursor.execute(query, params)
        
        # Fetch all records
        columns = [desc[0] for desc in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            # Convert datetime objects to ISO format strings
            for key, value in record.items():
                if isinstance(value, datetime.datetime):
                    record[key] = value.isoformat()
            records.append(record)
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'total_count': total_count,
            'returned_count': len(records),
            'offset': offset,
            'limit': limit,
            'order_by': order_by,
            'order_direction': order_direction,
            'emails': records,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting all emails: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error getting emails: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

@app.route('/api/workato/check-email-sent', methods=['POST'])
def workato_check_email_sent():
    """
    Workato endpoint to check if an email has already been sent to a contact.
    
    Expected input format:
    {
        "contact_email": "contact@example.com"
    }
    
    Returns:
    {
        "email_sent": true/false,
        "count": number of emails sent,
        "last_sent_at": timestamp,
        "campaign_name": "campaign name"
    }
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'error': 'Database not available',
                'message': 'PostgreSQL database is not connected'
            }), 503
        
        data = request.get_json() if request.is_json else {}
        
        if not data or 'contact_email' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required "contact_email" parameter',
                'timestamp': datetime.datetime.now().isoformat()
            }), 400
        
        contact_email = data.get('contact_email', '').lower().strip()
        
        if not contact_email:
            return jsonify({
                'status': 'error',
                'message': 'contact_email cannot be empty',
                'timestamp': datetime.datetime.now().isoformat()
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        cursor = conn.cursor()
        
        # Check if we've sent any emails to this recipient
        cursor.execute('''
            SELECT COUNT(*), MAX(sent_at)
            FROM email_tracking
            WHERE LOWER(recipient_email) = %s
        ''', (contact_email,))
        
        result = cursor.fetchone()
        
        if result and result[0] > 0:
            count = result[0]
            last_sent = result[1]
            
            # Get the campaign name from the most recent email
            cursor.execute('''
                SELECT campaign_name, subject, tracking_id
                FROM email_tracking
                WHERE LOWER(recipient_email) = %s
                ORDER BY sent_at DESC
                LIMIT 1
            ''', (contact_email,))
            campaign_result = cursor.fetchone()
            campaign = campaign_result[0] if campaign_result else "Unknown"
            subject = campaign_result[1] if campaign_result else None
            tracking_id = campaign_result[2] if campaign_result else None
            
            conn.close()
            
            return jsonify({
                'status': 'success',
                'email_sent': True,
                'count': count,
                'last_sent_at': last_sent.isoformat() if last_sent else None,
                'campaign_name': campaign,
                'last_subject': subject,
                'last_tracking_id': tracking_id,
                'timestamp': datetime.datetime.now().isoformat()
            })
        else:
            conn.close()
            return jsonify({
                'status': 'success',
                'email_sent': False,
                'count': 0,
                'last_sent_at': None,
                'campaign_name': None,
                'timestamp': datetime.datetime.now().isoformat()
            })
        
    except Exception as e:
        logger.error(f"❌ Error checking email sent status: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error checking email status: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get email tracking statistics with instant open filtering only."""
    try:
        if not DB_AVAILABLE:
            return jsonify({'error': 'Database not available'}), 503
            
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cursor = conn.cursor()
        
        # Get total emails sent
        cursor.execute('SELECT COUNT(*) FROM email_tracking')
        total_emails_sent = cursor.fetchone()[0]
        
        # Get all opens (no user agent filtering - only instant open filtering is applied at insert time)
        cursor.execute('SELECT COUNT(*) FROM email_opens')
        total_opens = cursor.fetchone()[0]
        
        # Calculate open rate
        open_rate = (total_opens / total_emails_sent * 100) if total_emails_sent > 0 else 0
        
        # Get recent opens
        cursor.execute('''
            SELECT tracking_id, opened_at, user_agent, ip_address 
            FROM email_opens 
            ORDER BY opened_at DESC 
            LIMIT 10
        ''')
        recent_opens = []
        for row in cursor.fetchall():
            recent_opens.append({
                'tracking_id': row[0],
                'opened_at': row[1].isoformat(),
                'user_agent': row[2],
                'ip_address': row[3]
            })
        
        # Get recent sends
        cursor.execute('''
            SELECT tracking_id, recipient_email, subject, sent_at 
            FROM email_tracking 
            ORDER BY sent_at DESC 
            LIMIT 10
        ''')
        recent_sends = []
        for row in cursor.fetchall():
            recent_sends.append({
                'tracking_id': row[0],
                'recipient_email': row[1],
                'subject': row[2],
                'sent_at': row[3].isoformat()
            })
        
        conn.close()
        
        return jsonify({
            'total_emails_sent': total_emails_sent,
            'total_opens': total_opens,
            'open_rate': round(open_rate, 2),
            'recent_opens': recent_opens,
            'recent_sends': recent_sends
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/env', methods=['GET'])
def debug_env():
    """Debug endpoint to check environment variables."""
    return jsonify({
        'gmail_client_id_exists': bool(os.environ.get('GMAIL_CLIENT_ID')),
        'gmail_client_secret_exists': bool(os.environ.get('GMAIL_CLIENT_SECRET')),
        'gmail_refresh_token_exists': bool(os.environ.get('GMAIL_REFRESH_TOKEN')),
        'openai_api_key_exists': bool(os.environ.get('OPENAI_API_KEY')),
        'openai_api_key_length': len(os.environ.get('OPENAI_API_KEY', '')),
        'openai_api_key_starts_with': os.environ.get('OPENAI_API_KEY', '')[:10] if os.environ.get('OPENAI_API_KEY') else '',
        'gmail_client_id_length': len(os.environ.get('GMAIL_CLIENT_ID', '')),
        'gmail_refresh_token_length': len(os.environ.get('GMAIL_REFRESH_TOKEN', ''))
    })

@app.route('/api/debug/openai', methods=['GET'])
def debug_openai():
    """Test OpenAI API connection."""
    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return jsonify({'error': 'OPENAI_API_KEY not set'}), 400
        
        client = OpenAI(api_key=api_key)
        
        # Simple test request
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Say 'Hello World'"}],
            max_tokens=10
        )
        
        return jsonify({
            'status': 'success',
            'response': response.choices[0].message.content,
            'api_key_length': len(api_key),
            'api_key_prefix': api_key[:10]
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

# 🔹 Workato Endpoints for Email Automation

@app.route('/api/workato/reply-to-emails', methods=['POST'])
def workato_reply_to_emails():
    """
    Workato endpoint to process email replies - ULTRA SIMPLE VERSION.
    
    Expected input format:
    {
        "email": "contact@example.com"
    }
    """
    try:
        data = request.get_json() if request.is_json else {}
        
        # Debug logging
        print(f"🔍 DEBUG: Received data: {data}")
        print(f"🔍 DEBUG: Data type: {type(data)}")
        print(f"🔍 DEBUG: Is JSON: {request.is_json}")
        print(f"🔍 DEBUG: Raw request data: {request.get_data()}")
        
        # Simple validation - only accept email field
        if not data or 'email' not in data:
            return jsonify({
                'status': 'error',
                'message': f'Missing required "email" parameter in request body. Received: {data}',
                'timestamp': datetime.datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        email = data['email']
        if not email or not isinstance(email, str):
            return jsonify({
                'status': 'error', 
                'message': 'Email must be a valid string',
                'timestamp': datetime.datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        print(f"📧 Workato triggered reply_to_emails at {datetime.datetime.now().isoformat()}")
        print(f"📊 Processing email: {email}")
        
        # Convert single email to account format for the function
        accounts = [{'email': email, 'name': email.split('@')[0].capitalize()}]
        
        # Call the function with Workato-provided accounts
        logger.info("🚀 Starting email processing...")
        result = reply_to_emails_with_accounts(accounts)
        logger.info("✅ Email processing completed")
        
        # Extract AI response content from results for clean text response
        ai_responses = []
        if 'responses' in result:
            for response in result['responses']:
                if 'ai_response' in response:
                    # Clean the AI response - remove HTML tags and line breaks
                    import re
                    clean_response = response['ai_response']
                    # Remove HTML tags
                    clean_response = re.sub(r'<[^>]+>', '', clean_response)
                    # Remove line breaks and extra whitespace
                    clean_response = clean_response.replace('\n', ' ').replace('\r', ' ').strip()
                    clean_response = re.sub(r'\s+', ' ', clean_response)
                    ai_responses.append(clean_response)
        
        return jsonify({
            'status': 'success',
            'message': 'Reply to emails completed successfully',
            'timestamp': datetime.datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_processed': result.get('emails_processed', 0),
            'replies_sent': result.get('replies_sent', 0),
            'ai_responses': ai_responses,
            'results': result
        })
        
    except Exception as e:
        logger.error(f"❌ Workato reply_to_emails error: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error processing replies: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat(),
            'emails_processed': 0
        }), 500

@app.route('/api/workato/reply-to-emails/status', methods=['POST'])
def workato_reply_status():
    """
    Get status of emails needing replies for Workato using provided accounts.
    
    Expected input format:
    {
        "accounts": [
            {
                "email": "contact@example.com",
                "name": "Contact Name", 
                "account_id": "SF_Account_ID",
                "contact_id": "SF_Contact_ID"
            }
        ]
    }
    """
    try:
        data = request.get_json() if request.is_json else {}
        
        # Validate input
        if not data or 'accounts' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required "accounts" parameter in request body',
                'timestamp': datetime.datetime.now().isoformat(),
                'emails_needing_replies': 0
            }), 400
        
        accounts = data['accounts']
        if not isinstance(accounts, list):
            return jsonify({
                'status': 'error', 
                'message': 'Accounts must be an array',
                'timestamp': datetime.datetime.now().isoformat(),
                'emails_needing_replies': 0
            }), 400
        
        # Get emails needing replies using Workato-provided accounts
        emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
        
        return jsonify({
            'status': 'success',
            'message': f'Found {len(emails_needing_replies)} emails needing replies',
            'timestamp': datetime.datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_needing_replies': len(emails_needing_replies),
            'emails': [
                {
                    'thread_id': email.get('threadId', 'No ID'),
                    'sender': email['sender'],
                    'subject': email['subject'],
                    'contact_name': email.get('contact_name', email['sender'].split("@")[0].capitalize()),
                    'account_id': email.get('account_id'),
                    'contact_id': email.get('contact_id')
                }
                for email in emails_needing_replies
            ]
        })
        
    except Exception as e:
        logger.error(f"❌ Workato reply status error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error getting reply status: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat(),
            'emails_needing_replies': 0
        }), 500

def parse_activities(activities):
    """
    Parse activities from various formats (string, dict, list) into a normalized list.
    Handles Workato/Salesforce format where activities might come as a string with Ruby hash syntax.
    
    Args:
        activities: Activities in various formats (string, dict, list)
    
    Returns:
        list: Normalized list of activity dictionaries
    """
    if not activities:
        return []
    
    # If it's already a list, return as-is
    if isinstance(activities, list):
        return activities
    
    # If it's a string, try to parse it
    if isinstance(activities, str):
        try:
            # First, try to parse as JSON
            import json
            parsed = json.loads(activities)
            # If it's a dict with a "Task" key, extract the array
            if isinstance(parsed, dict) and 'Task' in parsed:
                return parsed['Task']
            elif isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                # If it's a dict, try to find any array values
                for key, value in parsed.items():
                    if isinstance(value, list):
                        return value
                return []
        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, try to parse Ruby hash-like syntax
            try:
                import re
                import ast
                
                # Replace Ruby hash syntax => with Python dict syntax :
                # This is tricky because we need to handle nested structures
                # Strategy: Convert Ruby hash to Python dict syntax, then use ast.literal_eval
                
                normalized = activities.strip()
                
                # Replace => with : (Ruby hash syntax to Python dict syntax)
                # Be careful with spacing
                normalized = re.sub(r'\s*=>\s*', ': ', normalized)
                
                # Replace single quotes with double quotes for string keys/values
                # But preserve quotes inside strings - this is simplified
                # Convert 'key': to "key": 
                normalized = re.sub(r"'([^']+)':", r'"\1":', normalized)
                
                # Try to use ast.literal_eval to safely parse Python dict syntax
                try:
                    parsed = ast.literal_eval(normalized)
                    if isinstance(parsed, dict) and 'Task' in parsed:
                        return parsed['Task']
                    elif isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        # Look for any array values
                        for key, value in parsed.items():
                            if isinstance(value, list):
                                return value
                        return []
                except (ValueError, SyntaxError):
                    # If ast.literal_eval fails, try JSON again after more normalization
                    # Replace remaining single quotes
                    normalized = normalized.replace("'", '"')
                    parsed = json.loads(normalized)
                    if isinstance(parsed, dict) and 'Task' in parsed:
                        return parsed['Task']
                    elif isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        for key, value in parsed.items():
                            if isinstance(value, list):
                                return value
                        return []
            except (json.JSONDecodeError, ValueError, SyntaxError, Exception) as e:
                logger.warning(f"⚠️ Could not parse activities string: {e}")
                logger.debug(f"⚠️ Activities string preview: {activities[:500]}")
                # Last resort: simple string check for email indicators
                # If we can't parse, at least check if there are obvious email activity indicators
                activities_lower = activities.lower()
                email_indicators = ['sent ai-generated outreach', 'sent', 'email', 'outreach']
                if any(indicator in activities_lower for indicator in email_indicators):
                    logger.info("⚠️ Found email activity indicators in activities string (couldn't fully parse, but detected email activity)")
                    # Return a dummy activity to trigger the check
                    return [{'Type': 'Task', 'Subject': 'Sent AI-Generated Outreach', 'Status': 'Completed'}]
                return []
    
    # If it's a dict, try to extract arrays
    if isinstance(activities, dict):
        # Look for common keys like "Task", "tasks", etc.
        for key in ['Task', 'tasks', 'Activities', 'activities', 'EmailMessage', 'emailmessages']:
            if key in activities and isinstance(activities[key], list):
                return activities[key]
        # If no array found, return empty list
        return []
    
    return []

def normalize_activity(activity):
    """
    Normalize a Salesforce activity object to the expected format.
    Maps Salesforce field names to the format expected by check_if_email_already_sent.
    
    Args:
        activity: Activity dictionary from Salesforce
    
    Returns:
        dict: Normalized activity dictionary
    """
    if not isinstance(activity, dict):
        return {}
    
    # Map Salesforce fields to expected fields
    normalized = {
        'Type': activity.get('Type') or activity.get('TaskSubtype') or activity.get('attributes', {}).get('type', ''),
        'Subject': activity.get('Subject', ''),
        'Description': activity.get('Description') or activity.get('Description__c', ''),
        'Status': activity.get('Status', ''),
        'WhoId': activity.get('WhoId', ''),
        'WhatId': activity.get('WhatId', ''),
        'ToEmail': activity.get('ToEmail') or activity.get('ToAddress', ''),
        'ContactEmail': activity.get('ContactEmail', '')
    }
    
    # Clean up empty strings
    return {k: v for k, v in normalized.items() if v}

def check_if_email_already_sent(contact_email, activities=None):
    """
    Check if a first email has already been sent to this contact.
    Checks both the activities list (from Workato/Salesforce) and the database.
    
    Args:
        contact_email: The email address to check
        activities: Optional list of activities from Workato/Salesforce (can be string, dict, or list)
    
    Returns:
        tuple: (has_been_sent: bool, reason: str)
    """
    contact_email_lower = contact_email.lower().strip()
    
    # Parse and normalize activities
    activities_list = parse_activities(activities)
    normalized_activities = [normalize_activity(activity) for activity in activities_list]
    
    # Check 1: Look through activities list for email-related activities
    if normalized_activities:
        logger.info(f"📋 Checking {len(normalized_activities)} normalized activities for {contact_email}")
        for activity in normalized_activities:
            if not isinstance(activity, dict) or not activity:
                continue
                
            # Check for various activity types that indicate an email was sent
            activity_type = str(activity.get('Type', '')).lower()
            activity_subject = str(activity.get('Subject', '')).lower()
            activity_description = str(activity.get('Description', '')).lower()
            activity_status = str(activity.get('Status', '')).lower()
            
            # Check if this is an email-related activity (Task, EmailMessage, etc.)
            # Look for email indicators in type, subject, or description
            email_indicators = ['email', 'sent', 'outreach', 'personalized', 'ai-generated']
            is_email_activity = any(
                indicator in activity_type or 
                indicator in activity_subject or 
                indicator in activity_description
                for indicator in email_indicators
            )
            
            # Also check if Type is explicitly an email type
            email_types = ['email', 'emailmessage', 'task']
            if activity_type in email_types:
                is_email_activity = True
            
            if is_email_activity:
                # Check if it's related to this contact
                activity_who_id = activity.get('WhoId', '')
                activity_what_id = activity.get('WhatId', '')
                activity_to_email = str(activity.get('ToEmail', '')).lower()
                activity_contact_email = str(activity.get('ContactEmail', '')).lower()
                
                # Check if activity is completed/sent (not just created)
                # For Tasks with "Sent" in subject, consider them as completed
                is_completed = (activity_status in ['completed', 'sent', 'closed'] or 
                               'sent' in activity_subject) if activity_status or activity_subject else True
                
                # If the activity has the contact's email or is related to them
                # Since WhoId might be nil in the data, we'll check the subject for email indicators
                if (contact_email_lower in activity_to_email or 
                    contact_email_lower in activity_contact_email or
                    (activity_who_id and is_completed) or 
                    (activity_what_id and is_completed) or
                    ('sent' in activity_subject and 'outreach' in activity_subject)):
                    logger.info(f"📧 Found email activity in activities list for {contact_email}: {activity_subject or activity_type}")
                    return True, f"Email activity found in activities: {activity_subject or activity_type}"
    
    # Check 2: Query database for previously sent emails to this recipient
    if DB_AVAILABLE:
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                # Check if we've sent any emails to this recipient
                cursor.execute('''
                    SELECT COUNT(*), MAX(sent_at)
                    FROM email_tracking
                    WHERE LOWER(recipient_email) = %s
                ''', (contact_email_lower,))
                
                result = cursor.fetchone()
                
                if result and result[0] > 0:
                    count = result[0]
                    last_sent = result[1]
                    
                    # Get the campaign name from the most recent email
                    cursor.execute('''
                        SELECT campaign_name
                        FROM email_tracking
                        WHERE LOWER(recipient_email) = %s
                        ORDER BY sent_at DESC
                        LIMIT 1
                    ''', (contact_email_lower,))
                    campaign_result = cursor.fetchone()
                    campaign = campaign_result[0] if campaign_result else "Unknown"
                    
                    conn.close()
                    logger.info(f"📧 Found {count} previously sent email(s) to {contact_email} in database (last sent: {last_sent})")
                    return True, f"Email already sent to this recipient ({count} time(s), last: {last_sent}, campaign: {campaign})"
                
                conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Error checking database for existing emails: {e}")
    
    return False, "No previous email found"

@app.route('/api/workato/send-new-email', methods=['POST'])
def workato_send_new_email():
    """Workato endpoint for sending new personalized emails - replicates send_new_email from 2025_hackathon.py."""
    try:
        # Add debugging for request data
        logger.info(f"🔍 DEBUG: Received request to send-new-email")
        logger.info(f"🔍 DEBUG: Content-Type: {request.content_type}")
        logger.info(f"🔍 DEBUG: Is JSON: {request.is_json}")
        logger.info(f"🔍 DEBUG: Raw data: {request.get_data()}")
        
        try:
            data = request.get_json()
            logger.info(f"🔍 DEBUG: Parsed JSON data: {data}")
        except Exception as json_error:
            logger.error(f"❌ JSON parsing error: {json_error}")
            return jsonify({
                "status": "error",
                "message": f"Invalid JSON format: {str(json_error)}",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "No JSON data provided",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        logger.info(f"📧 Workato triggered send_new_email at {datetime.datetime.now().isoformat()}")
        logger.info(f"📊 Processing contact data from Workato")
        
        # Extract contact information from Workato request
        contact_name = data.get('contact_name', '')
        contact_email = data.get('contact_email', '')
        contact_title = data.get('contact_title', '')
        contact_phone = data.get('contact_phone', '')
        
        # Account information with proper type conversion
        account_name = data.get('account_name', '')
        account_industry = data.get('account_industry', 'Business')
        account_website = data.get('account_website', '')
        account_description = data.get('account_description', '')
        
        # Convert numeric fields safely
        try:
            account_revenue = int(data.get('account_revenue', 0)) if data.get('account_revenue', '') else 0
        except (ValueError, TypeError):
            account_revenue = 0
            
        try:
            account_employees = int(data.get('account_employees', 0)) if data.get('account_employees', '') else 0
        except (ValueError, TypeError):
            account_employees = 0
            
        try:
            account_gmv = float(data.get('account_gmv', 0)) if data.get('account_gmv', '') else 0
        except (ValueError, TypeError):
            account_gmv = 0
        
        account_city = data.get('account_city', '')
        account_state = data.get('account_state', '')
        account_country = data.get('account_country', '')
        account_id = data.get('account_id', '')
        
        # Extract activities from Workato request (can be string, dict, or list)
        activities = data.get('activities', [])
        if activities:
            logger.info(f"📋 Received activities from Workato (raw type: {type(activities).__name__})")
            if isinstance(activities, str):
                logger.info(f"📋 Activities string preview: {activities[:200]}...")
        
        # Sender information
        sender_name = "Jake Morgan"
        sender_title = "Business Development"
        
        if not contact_email:
            return jsonify({
                "status": "error",
                "message": "Missing required 'contact_email' parameter",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        # Check if email has already been sent (activities will be parsed inside the function)
        has_been_sent, reason = check_if_email_already_sent(contact_email, activities)
        
        if has_been_sent:
            logger.info(f"⏭️ Skipping email send to {contact_email} - {reason}")
            return jsonify({
                "status": "skipped",
                "message": f"Email already sent to this contact - {reason}",
                "timestamp": datetime.datetime.now().isoformat(),
                "contact": contact_name,
                "account": account_name,
                "reason": reason,
                "emails_sent": 0
            }), 200
        
        logger.info(f"📧 Sending personalized email to {contact_name} ({contact_email})")
        logger.info(f"   Account: {account_name} ({account_industry})")
        logger.info(f"   Website: {account_website}")
        
        # Generate personalized subject and content using AI
        subject_line, email_content = generate_message(
            merchant_name=contact_name,
            last_activity="Recent",
            merchant_industry=account_industry,
            merchant_website=account_website,
            sender_name=sender_name,
            account_description=account_description,
            account_revenue=account_revenue,
            account_employees=account_employees,
            account_location=f"{account_city}, {account_state}".strip(", ") if account_city else "",
            contact_title=contact_title,
            account_gmv=account_gmv
        )
        
        # Format email with HTML template
        formatted_email = format_pardot_email(
            first_name=contact_name,
            email_content=email_content,
            recipient_email=contact_email,
            sender_name=sender_name
        )
        
        # Send email with tracking
        email_result = send_email(
            to_email=contact_email,
            merchant_name=contact_name,
            subject_line=subject_line,
            email_content=formatted_email,
            campaign_name="Workato Personalized Outreach"
        )
        
        email_status = email_result['status'] if isinstance(email_result, dict) else email_result
        tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""
        
        # Salesforce logging removed
        
        logger.info(f"✅ Personalized email sent successfully to {contact_name}")
        
        # Clean email content - remove line breaks and extra whitespace
        clean_email_body = email_content.replace('\n', ' ').replace('\r', ' ').strip()
        # Remove multiple spaces
        import re
        clean_email_body = re.sub(r'\s+', ' ', clean_email_body)
        
        return jsonify({
            "status": "success",
            "message": "Personalized email sent successfully",
            "timestamp": datetime.datetime.now().isoformat(),
            "contact": contact_name,
            "account": account_name,
            "email_status": email_status + tracking_info,
            "subject": subject_line,
            "email_body": clean_email_body,
            "tracking_id": email_result.get('tracking_id') if isinstance(email_result, dict) else None,
            "tracking_url": email_result.get('tracking_url') if isinstance(email_result, dict) else None,
            "emails_sent": 1
        })
        
    except Exception as e:
        logger.error(f"❌ Workato send_new_email error: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error sending personalized email: {str(e)}",
            "timestamp": datetime.datetime.now().isoformat()
        }), 500

def get_google_sheets_credentials():
    """Get Google Sheets API credentials from environment variables."""
    try:
        credentials_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
        if not credentials_json:
            logger.warning("GOOGLE_SHEETS_CREDENTIALS_JSON environment variable not set")
            logger.warning("Please set GOOGLE_SHEETS_CREDENTIALS_JSON in Railway Variables")
            return None
        
        # Strip whitespace in case it was pasted with extra spaces
        credentials_json = credentials_json.strip()
        
        # Check if it's empty after stripping
        if not credentials_json:
            logger.error("GOOGLE_SHEETS_CREDENTIALS_JSON is empty")
            return None
        
        import json
        try:
            creds_info = json.loads(credentials_json)
        except json.JSONDecodeError as json_error:
            logger.error(f"❌ Invalid JSON in GOOGLE_SHEETS_CREDENTIALS_JSON: {json_error}")
            logger.error(f"   First 100 chars: {credentials_json[:100]}")
            logger.error("   Make sure you pasted the entire JSON file contents")
            return None
        
        # Validate required fields
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds_info]
        if missing_fields:
            logger.error(f"❌ Missing required fields in credentials: {missing_fields}")
            return None
        
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        logger.info("✅ Google Sheets credentials loaded successfully")
        logger.info(f"   Service account: {creds_info.get('client_email', 'unknown')}")
        return creds
    except Exception as e:
        logger.error(f"❌ Error getting Google Sheets credentials: {e}")
        import traceback
        traceback.print_exc()
        return None

def write_to_google_sheets(records):
    """
    Write email tracking records to Google Sheets.
    
    Args:
        records: List of dictionaries with email tracking data
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        if not GSPREAD_AVAILABLE:
            return False, "gspread library not available"
        
        # Get credentials
        creds = get_google_sheets_credentials()
        if not creds:
            return False, "Google Sheets credentials not available"
        
        # Connect to Google Sheets
        gc = gspread.authorize(creds)
        
        # Get spreadsheet ID from environment variable
        spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID', '14fg3zEBhzyEILrT85imjNtOkasybpOM2FspbE-Wx9Rc')
        sheet_name = os.getenv('GOOGLE_SHEETS_NAME', 'Send_Logs')
        
        try:
            spreadsheet = gc.open_by_key(spreadsheet_id)
        except Exception as e:
            return False, f"Could not access Google Sheet: {str(e)}"
        
        # Get or create worksheet
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            # Clear existing data (optional - comment out if you want to append)
            # worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            # Create worksheet if it doesn't exist
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
        
        # Prepare headers
        if records:
            headers = list(records[0].keys())
            # Format headers nicely
            header_map = {
                'id': 'ID',
                'tracking_id': 'Tracking ID',
                'recipient_email': 'Recipient Email',
                'sender_email': 'Sender Email',
                'subject': 'Subject',
                'campaign_name': 'Campaign Name',
                'sent_at': 'Sent At',
                'open_count': 'Open Count',
                'last_opened_at': 'Last Opened At',
                'created_at': 'Created At'
            }
            formatted_headers = [header_map.get(h, h.replace('_', ' ').title()) for h in headers]
        else:
            formatted_headers = []
            headers = []
        
        # Prepare data rows
        data_rows = [formatted_headers]
        for record in records:
            row = []
            for header in headers:
                value = record.get(header, '')
                # Format datetime objects
                if isinstance(value, datetime.datetime):
                    value = value.strftime('%Y-%m-%d %H:%M:%S')
                elif value is None:
                    value = ''
                row.append(str(value))
            data_rows.append(row)
        
        # Update worksheet
        if data_rows:
            # Clear and write new data (or append - see comment above)
            worksheet.clear()
            worksheet.update('A1', data_rows)
            
            # Format header row
            worksheet.format('A1:Z1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
        
        return True, f"Successfully wrote {len(records)} records to {sheet_name}"
        
    except Exception as e:
        logger.error(f"❌ Error writing to Google Sheets: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}"

@app.route('/api/workato/dump-email-tracking', methods=['POST', 'GET'])
def workato_dump_email_tracking():
    """
    Railway endpoint to trigger email tracking data dump.
    Can be called manually or by an external cron service.
    
    Optional query parameters (GET) or body (POST):
    {
        "format": "csv|json|both",  # Default: both
        "limit": 1000,              # Max records (default: all)
        "since_days": 7,            # Last N days
        "date": "2025-11-01"        # From specific date
    }
    
    Returns JSON response with dump status.
    Note: Files are saved to ephemeral filesystem on Railway.
    For persistent storage, modify to upload to cloud storage.
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        # Support both GET and POST
        if request.method == 'GET':
            data = request.args.to_dict()
        else:
            data = request.get_json() if request.is_json else {}
        
        # Parse parameters
        export_format = data.get('format', 'both')
        try:
            limit = int(data.get('limit')) if data.get('limit') else None
        except (ValueError, TypeError):
            limit = None
        
        try:
            since_days = int(data.get('since_days')) if data.get('since_days') else None
        except (ValueError, TypeError):
            since_days = None
        
        date_filter = data.get('date', None)
        
        # Calculate date filter if since_days is provided
        if since_days:
            date_filter = (datetime.datetime.now() - datetime.timedelta(days=since_days)).date().isoformat()
        
        logger.info(f"📊 Starting email tracking dump via API...")
        logger.info(f"   Format: {export_format}")
        if limit:
            logger.info(f"   Limit: {limit}")
        if date_filter:
            logger.info(f"   Date filter: {date_filter}")
        
        # Execute dump query
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                id,
                tracking_id,
                recipient_email,
                sender_email,
                subject,
                campaign_name,
                sent_at,
                open_count,
                last_opened_at,
                created_at
            FROM email_tracking
        """
        
        params = []
        conditions = []
        
        if date_filter:
            conditions.append("sent_at >= %s")
            params.append(date_filter)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY sent_at DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        records = []
        for row in rows:
            record = dict(zip(columns, row))
            # Convert datetime to ISO format
            for key, value in record.items():
                if isinstance(value, datetime.datetime):
                    record[key] = value.isoformat()
            records.append(record)
        
        conn.close()
        
        logger.info(f"📊 Retrieved {len(records)} records")
        
        # Write to Google Sheets if credentials are available
        sheets_success = False
        sheets_message = ""
        if GSPREAD_AVAILABLE and records:
            sheets_success, sheets_message = write_to_google_sheets(records)
            if sheets_success:
                logger.info(f"✅ Successfully wrote {len(records)} records to Google Sheets")
            else:
                logger.warning(f"⚠️ Google Sheets write failed: {sheets_message}")
        
        # Return JSON response
        response_data = {
            'status': 'success',
            'message': f'Retrieved {len(records)} email tracking records',
            'count': len(records),
            'format': export_format,
            'timestamp': datetime.datetime.now().isoformat(),
            'google_sheets': {
                'written': sheets_success,
                'message': sheets_message
            },
            'emails': records
        }
        
        # If format includes CSV, add CSV data as string
        if export_format in ['csv', 'both']:
            import csv
            import io
            output = io.StringIO()
            if records:
                writer = csv.DictWriter(output, fieldnames=records[0].keys())
                writer.writeheader()
                for record in records:
                    cleaned = {k: (v if v is not None else '') for k, v in record.items()}
                    writer.writerow(cleaned)
            response_data['csv_data'] = output.getvalue()
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error dumping email tracking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error dumping data: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
