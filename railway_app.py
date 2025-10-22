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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Email configuration (same as 2025_hackathon.py)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "jake.morgan@affirm.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

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
    """Generate an AI response using OpenAI."""
    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        logger.info(f"OpenAI API key exists: {bool(api_key)}, length: {len(api_key) if api_key else 0}")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        # Build conversation context if provided
        conversation_context = ""
        if conversation_history:
            conversation_context = f"\n\nConversation Context:\n{conversation_history}"
        
        prompt = f"""
You are Jake Morgan, Business Development at Affirm. Write a professional, helpful email response.

Email to respond to:
From: {recipient_name}
Body: {email_body}

{conversation_context}

Write a professional response that:
1. Addresses their specific questions or concerns
2. Provides helpful information about Affirm's services
3. Maintains a friendly, professional tone
4. Includes a clear call-to-action if appropriate

Format your response as:
**Subject Line:** [subject]
**Email Body:** [body]
"""
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7
        )
        
        response_text = response.choices[0].message.content
        
        # Extract Subject Line and Email Body using regex
        subject_line_match = re.search(r"\*\*Subject Line:\*\*\s*(.*)", response_text)
        email_body_match = re.search(r"\*\*Email Body:\*\*\s*(.*)", response_text, re.DOTALL)

        subject_line = subject_line_match.group(1).strip() if subject_line_match else f"Re: Your Message"
        email_body = email_body_match.group(1).strip() if email_body_match else f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"

        # Format with HTML template (same as 2025_hackathon.py)
        return format_pardot_email(first_name=recipient_name, 
                                   email_content=email_body, 
                                   recipient_email="recipient@email.com", 
                                   sender_name=sender_name)
        
    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        if hasattr(e, 'response'):
            logger.error(f"OpenAI response: {e.response}")
        fallback_response = f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"
        return format_pardot_email(first_name=recipient_name, 
                                   email_content=fallback_response, 
                                   recipient_email="recipient@email.com", 
                                   sender_name=sender_name)

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
        
        # Send email via Gmail API (Railway network can't reach SMTP)
        # But use the same email formatting as 2025_hackathon.py
        try:
            creds = authenticate_gmail()
            service = build('gmail', 'v1', credentials=creds)
            
            # Create message for Gmail API with same formatting as SMTP
            message = MIMEMultipart()
            message["to"] = to_email
            message["subject"] = subject
            message["from"] = "jake.morgan@affirm.com"
            
            # Add threading headers (same as SMTP version)
            if original_message_id:
                original_message_id_header = get_original_message_id(original_message_id)
                if original_message_id_header:
                    message['In-Reply-To'] = original_message_id_header
                    message['References'] = original_message_id_header
                else:
                    message['In-Reply-To'] = f"<{original_message_id}@gmail.com>"
                    message['References'] = f"<{original_message_id}@gmail.com>"
            
            message.attach(MIMEText(tracked_email_content, "html"))
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            message_body = {'raw': raw_message}
            
            response = service.users().messages().send(userId='me', body=message_body).execute()
            logger.info("📧 Email sent successfully via Gmail API!")
            logger.info(f"📧 Gmail Message ID: {response.get('id')}")
            
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
    """Process email replies using accounts provided by Workato instead of querying Salesforce."""
    try:
        # Get emails needing replies using the provided accounts
        emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
        responses = []

        logger.info(f"🔍 DEBUG: Found {len(emails_needing_replies)} emails needing replies")
        if emails_needing_replies:
            logger.info(f"🔍 DEBUG: First email details: {emails_needing_replies[0]}")
        else:
            logger.info("🔍 DEBUG: No emails found - this might be why no emails are sent")

        logger.info(f"Processing {len(emails_needing_replies)} threads individually...")
        
        # Process each thread individually
        for i, email in enumerate(emails_needing_replies):
            thread_id = email.get('threadId', 'No ID')
            logger.info(f"Processing thread {i+1}/{len(emails_needing_replies)}: {thread_id}")
            
            # Extract contact information
            contact_name = email.get('contact_name', email['sender'].split("@")[0].capitalize())
            contact_email = email['sender']
            account_id = email.get('account_id')
            contact_id = email.get('contact_id')
            
            # Sender information
            sender_name = "Jake Morgan"
            
            # For single email, use it as the conversation context
            conversation_content = f"📧 EMAIL TO RESPOND TO:\nSubject: {email['subject']}\nFrom: {email['sender']}\nBody: {email['body']}"
            
            try:
                # Generate AI response using the email content
                ai_response = generate_ai_response(email['body'], sender_name, contact_name, conversation_content)
                
                # Send threaded reply
                email_result = send_threaded_email_reply(
                    to_email=contact_email,
                    subject=f"Re: {email['subject']}",
                    reply_content=ai_response,
                    original_message_id=email['id'],  # Use Gmail message ID like 2025_hackathon.py
                    sender_name=sender_name
                )
                
                # Log success
                response_info = {
                    'thread_id': thread_id,
                    'contact_name': contact_name,
                    'contact_email': contact_email,
                    'subject': email['subject'],
                    'status': 'success',
                    'account_id': account_id,
                    'contact_id': contact_id
                }
                
                responses.append(response_info)
                logger.info(f"Reply sent successfully to {contact_name} ({contact_email})")
                
            except Exception as e:
                logger.error(f"Error processing email for {contact_name}: {e}")
                response_info = {
                    'thread_id': thread_id,
                    'contact_name': contact_name,
                    'contact_email': contact_email,
                    'subject': email['subject'],
                    'status': 'error',
                    'error': str(e),
                    'account_id': account_id,
                    'contact_id': contact_id
                }
                responses.append(response_info)
        
        # Return results
        successful_replies = len([r for r in responses if r['status'] == 'success'])
        
        return {
            'message': f'Processed {len(emails_needing_replies)} conversation threads',
            'emails_processed': len(emails_needing_replies),
            'replies_sent': successful_replies,
            'responses': responses
        }
        
    except Exception as e:
        logger.error(f"Error in reply_to_emails_with_accounts: {e}")
        raise e

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
    
    # Check each conversation thread - only the latest email per thread
    for thread_id, emails_in_thread in thread_emails.items():
        # Sort emails by date to get the latest one
        emails_in_thread.sort(key=lambda x: x.get('date', ''), reverse=True)
        latest_email = emails_in_thread[0]  # Most recent email in this thread
        
        # Check if this thread needs a reply (is the latest message from the contact?)
        if not has_been_replied_to(latest_email['id'], service):
            emails_needing_replies.append(latest_email)
            logger.info(f"Conversation thread {thread_id} from {latest_email['sender']} needs a reply")
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
            'workato_reply_status': 'POST /api/workato/reply-to-emails/status'
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
        
        return jsonify({
            'status': 'success',
            'message': 'Reply to emails completed successfully',
            'timestamp': datetime.datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_processed': result.get('emails_processed', 0),
            'replies_sent': result.get('replies_sent', 0),
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
