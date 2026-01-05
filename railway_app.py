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
import hashlib
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

# OpenAI configuration
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")  # Can be changed to "gpt-3.5-turbo", "gpt-4-turbo", etc.

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sfdc_task_id VARCHAR(255),
                status VARCHAR(50) DEFAULT 'AI Outbound Email'
            )
        ''')
        
        # Add sfdc_task_id column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS sfdc_task_id VARCHAR(255)')
        except Exception as e:
            # Column might already exist, ignore error
            logger.debug(f"sfdc_task_id column check: {e}")
        
        # Add status column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT \'AI Outbound Email\'')
            # Update existing records without status to have default status
            cursor.execute('UPDATE email_tracking SET status = \'AI Outbound Email\' WHERE status IS NULL')
            # Update records with opens to 'Email Open'
            cursor.execute('''
                UPDATE email_tracking 
                SET status = 'Email Open' 
                WHERE open_count > 0 AND status = 'AI Outbound Email'
            ''')
        except Exception as e:
            # Column might already exist, ignore error
            logger.debug(f"status column check: {e}")
        
        # Add version_endpoint column to track which prompt version was used
        try:
            cursor.execute('ALTER TABLE email_tracking ADD COLUMN IF NOT EXISTS version_endpoint VARCHAR(255)')
        except Exception as e:
            logger.debug(f"version_endpoint column check: {e}")
        
        # Remove old variant_endpoint column if it exists
        try:
            cursor.execute('ALTER TABLE email_tracking DROP COLUMN IF EXISTS variant_endpoint')
            logger.info("✅ Removed old variant_endpoint column")
        except Exception as e:
            logger.debug(f"variant_endpoint column removal check: {e}")
        
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
        
        # Prompt versions table for A/B testing (also stores default prompts with version_letter = 'DEFAULT')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id SERIAL PRIMARY KEY,
                version_name VARCHAR(255) NOT NULL,
                prompt_type VARCHAR(50) NOT NULL,
                prompt_content TEXT NOT NULL,
                version_letter VARCHAR(10) NOT NULL,
                endpoint_path VARCHAR(255) NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prompt_type, version_letter)
            )
        ''')
        
        # Test merchants table for prompt testing
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_merchants (
                id SERIAL PRIMARY KEY,
                merchant_name VARCHAR(255) NOT NULL,
                contact_email VARCHAR(255),
                contact_title VARCHAR(255),
                merchant_industry VARCHAR(255),
                merchant_website VARCHAR(255),
                account_description TEXT,
                account_revenue DECIMAL(15, 2),
                account_employees INTEGER,
                account_location VARCHAR(255),
                account_gmv DECIMAL(15, 2),
                last_activity VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

def normalize_email(email):
    """
    Normalize email address by removing Gmail aliases (+alias part).
    Example: sanjaydhawan1997+testdecfour@gmail.com -> sanjaydhawan1997@gmail.com
    """
    if not email:
        return email
    
    email = email.lower().strip()
    
    # Extract email from "Name <email@domain.com>" format
    if '<' in email and '>' in email:
        email = email.split('<')[1].split('>')[0]
    
    # Remove Gmail aliases (everything after + and before @)
    if '+' in email and '@' in email:
        local_part, domain = email.split('@', 1)
        # Remove everything after the + sign
        local_part = local_part.split('+')[0]
        email = f"{local_part}@{domain}"
    
    return email

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
    """
    Check if the LATEST message in the thread (that's still in INBOX) is from us (Jake Morgan).
    Only considers messages that are still in the inbox (not deleted/trashed).
    
    If the latest message is from Jake Morgan, also checks if it's been at least 27 hours.
    Returns True (don't reply) if:
    - Latest message is from Jake AND it's been less than 27 hours
    Returns False (can reply) if:
    - Latest message is NOT from Jake, OR
    - Latest message is from Jake but it's been 27+ hours
    """
    try:
        import time
        
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
            
        logger.info(f"📧 Thread {thread_id} has {len(messages)} total messages")
        
        # Filter to messages that are accessible (in INBOX or SENT, not deleted/trashed)
        # We need to check SENT folder too because Jake's replies go to SENT, not INBOX
        # Also collect their internal dates for proper chronological sorting
        accessible_messages_with_dates = []
        for msg in messages:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                labels = msg_data.get('labelIds', [])
                # Include messages that are in INBOX or SENT (not in TRASH)
                # This ensures we catch Jake's replies which go to SENT folder
                if 'TRASH' not in labels and ('INBOX' in labels or 'SENT' in labels):
                    internal_date = msg_data.get('internalDate', 0)
                    headers = msg_data['payload'].get('headers', [])
                    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                    
                    # Convert internal_date to readable time
                    import datetime
                    readable_time = datetime.datetime.fromtimestamp(int(internal_date) / 1000).strftime('%Y-%m-%d %H:%M:%S') if internal_date else 'Unknown'
                    
                    location = 'SENT' if 'SENT' in labels else 'INBOX'
                    accessible_messages_with_dates.append({
                        'message': msg,
                        'internal_date': int(internal_date) if internal_date else 0,
                        'labels': labels,
                        'sender': sender,
                        'subject': subject,
                        'date_str': date_str,
                        'readable_time': readable_time,
                        'location': location
                    })
                    
                    logger.info(f"  📨 Message {msg['id']}: From={sender}, Time={readable_time}, Location={location}, Subject={subject[:50]}")
            except Exception as e:
                # If message was deleted, skip it
                logger.debug(f"Message {msg['id']} not accessible (likely deleted): {e}")
                continue
        
        if not accessible_messages_with_dates:
            # No accessible messages, consider it as needing reply
            logger.info(f"Thread {thread_id} has no accessible messages (INBOX or SENT), considering as needing reply")
            return False
        
        logger.info(f"📧 Found {len(accessible_messages_with_dates)} accessible messages (INBOX or SENT)")
        
        # Sort by internal date (chronological order) to get the actual latest message
        accessible_messages_with_dates.sort(key=lambda x: x['internal_date'])
        latest_message_data = accessible_messages_with_dates[-1]
        latest_message = latest_message_data['message']
        latest_internal_date = latest_message_data['internal_date']
        latest_labels = latest_message_data['labels']
        latest_sender_info = latest_message_data['sender']
        latest_readable_time = latest_message_data['readable_time']
        latest_location = latest_message_data['location']
        
        logger.info(f"📧 LATEST MESSAGE in thread {thread_id}:")
        logger.info(f"  📨 ID: {latest_message['id']}")
        logger.info(f"  👤 From: {latest_sender_info}")
        logger.info(f"  🕐 Time: {latest_readable_time} (internal_date: {latest_internal_date})")
        logger.info(f"  📍 Location: {latest_location}")
        
        # Get full message data for the latest message
        latest_msg_data = service.users().messages().get(userId='me', id=latest_message['id']).execute()
        headers = latest_msg_data['payload'].get('headers', [])
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        
        # If message is in SENT folder, it's from us (Jake Morgan)
        # Also check the sender header for jake.morgan@affirm.com
        is_from_us = False
        if 'SENT' in latest_labels:
            # Messages in SENT folder are from us
            is_from_us = True
            logger.info(f"Thread {thread_id} - latest message is in SENT folder (from us)")
        elif sender and 'jake.morgan@affirm.com' in sender.lower():
            # Check sender header as backup
            is_from_us = True
            logger.info(f"Thread {thread_id} - latest message From header indicates it's from us: {sender}")
        else:
            logger.info(f"Thread {thread_id} - latest message is NOT from us. Sender: {sender}, Labels: {latest_labels}")
        
        if is_from_us:
            # Check if Jake's reply was sent within the last 27 hours
            current_time_ms = int(time.time() * 1000)  # Current time in milliseconds
            time_since_reply_ms = current_time_ms - latest_internal_date
            hours_since_reply = time_since_reply_ms / (1000 * 60 * 60)  # Convert to hours
            
            location = "SENT" if 'SENT' in latest_labels else "INBOX"
            if hours_since_reply < 27:
                logger.info(f"Thread {thread_id} - latest message is from us in {location} (replied {hours_since_reply:.1f} hours ago, less than 27 hours - skipping)")
                return True  # Don't reply, it's been less than 27 hours
            else:
                logger.info(f"Thread {thread_id} - latest message is from us in {location} (replied {hours_since_reply:.1f} hours ago, 27+ hours - can reply)")
                return False  # Can reply, it's been 27+ hours
        else:
            location = "SENT" if 'SENT' in latest_labels else "INBOX"
            logger.info(f"Thread {thread_id} - latest message in {location} is from {sender} (needs reply)")
            return False  # Can reply, latest message is not from us
        
    except Exception as e:
        logger.error(f"Error checking reply status for email {email_id}: {e}")
        return False

def generate_ai_response(email_body, sender_name, recipient_name, conversation_history=None, prompt_template=None):
    """
    Generates an AI response using the same detailed prompt as generate_message.
    Creates a professional, Affirm-branded email response with full conversation context.
    Can use a custom prompt_template if provided, otherwise reads from REPLY_EMAIL_PROMPT_TEMPLATE environment variable.
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

    # Use custom prompt template if provided, otherwise try environment variable
    reply_email_prompt_template = prompt_template or os.getenv('REPLY_EMAIL_PROMPT_TEMPLATE')
    prompt_source = "custom" if prompt_template else ("env_variable" if os.getenv('REPLY_EMAIL_PROMPT_TEMPLATE') else "default")
    
    if reply_email_prompt_template:
        # Use custom template (from parameter, environment variable, or default)
        try:
            prompt = reply_email_prompt_template.format(
                AFFIRM_VOICE_GUIDELINES=AFFIRM_VOICE_GUIDELINES,
                recipient_name=recipient_name,
                sender_name=sender_name,
                conversation_context=conversation_context,
                email_body=email_body
            )
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
            source_description = "Custom prompt (from test/API)" if prompt_template else ("REPLY_EMAIL_PROMPT_TEMPLATE environment variable" if os.getenv('REPLY_EMAIL_PROMPT_TEMPLATE') else "Default prompt template (hardcoded)")
            logger.info(f"📝 PROMPT USED FOR REPLY EMAIL:")
            logger.info(f"   Source: {source_description}")
            logger.info(f"   Endpoint: /api/workato/reply-to-emails (Default)")
            logger.info(f"   Prompt Type: reply-email")
            logger.info(f"   Prompt Hash: {prompt_hash}")
            logger.info(f"   Prompt Length: {len(prompt)} characters")
            logger.info(f"   Recipient: {recipient_name}")
            logger.info(f"   Conversation History Length: {len(conversation_history) if conversation_history else 0} characters")
            logger.info(f"   Full Prompt Content:\n{'='*80}\n{prompt}\n{'='*80}")
        except KeyError as e:
            logger.warning(f"⚠️ REPLY_EMAIL_PROMPT_TEMPLATE missing variable {e}, using default")
            reply_email_prompt_template = None
    
    # Default prompt if no custom template or formatting failed
    if not reply_email_prompt_template:
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

    For all support, refer to customercare@affirm.com Only.
    """

    # Log the prompt being used (for default prompt)
    if prompt_source == "default":
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        logger.info(f"📝 PROMPT USED FOR REPLY EMAIL:")
        logger.info(f"   Source: Default prompt template (hardcoded)")
        logger.info(f"   Endpoint: /api/workato/reply-to-emails (Default)")
        logger.info(f"   Prompt Type: reply-email")
        logger.info(f"   Prompt Hash: {prompt_hash}")
        logger.info(f"   Prompt Length: {len(prompt)} characters")
        logger.info(f"   Recipient: {recipient_name}")
        logger.info(f"   Conversation History Length: {len(conversation_history) if conversation_history else 0} characters")
        logger.info(f"   Full Prompt Content:\n{'='*80}\n{prompt}\n{'='*80}")

    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        logger.info(f"🤖 Using OpenAI model: {OPENAI_MODEL}")
        logger.info(f"🤖 Sending prompt to OpenAI...")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
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

def generate_message(merchant_name, last_activity, merchant_industry, merchant_website, sender_name, account_description="", account_revenue=0, account_employees=0, account_location="", contact_title="", account_gmv=0, prompt_template=None):
    """
    Creates an Affirm-branded outreach email using AI with detailed Salesforce data.
    Can use a custom prompt template if provided, otherwise uses default.
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
    
    # Use custom prompt template if provided, otherwise use default
    prompt_source = "default"
    if prompt_template:
        # Format the custom template with variables
        try:
            formatted_prompt = prompt_template.format(
                AFFIRM_VOICE_GUIDELINES=AFFIRM_VOICE_GUIDELINES,
                merchant_name=merchant_name,
                contact_title_str=contact_title_str,
                merchant_industry_str=merchant_industry_str,
                merchant_website_str=merchant_website_str,
                sender_name=sender_name,
                account_description_str=account_description_str,
                account_revenue_str=account_revenue_str,
                account_gmv_str=account_gmv_str,
                account_employees_str=account_employees_str,
                account_location_str=account_location_str
            )
            
            # If the formatted prompt is very short (< 100 chars), it's likely just an instruction
            # Wrap it in a proper prompt structure
            if len(formatted_prompt.strip()) < 100 and '{' not in prompt_template:
                # This looks like a simple instruction, not a full prompt template
                # Wrap it in a proper prompt structure
                prompt = f"""
{AFFIRM_VOICE_GUIDELINES}

**TASK:** {formatted_prompt}

**CONTEXT:**
- Contact Name: {merchant_name}
- Contact Title: {contact_title_str}
- Industry: {merchant_industry_str}
- Website: {merchant_website_str}
- Sender: {sender_name}
- Account Description: {account_description_str}
- Annual Revenue: {account_revenue_str}
- Trailing 12M GMV: {account_gmv_str}
- Employees: {account_employees_str}
- Location: {account_location_str}

**OUTPUT FORMAT:**
- **Subject Line:** [Concise subject line]
- **Email Body:** [Email message]
"""
            else:
                # Use the formatted prompt as-is (it's a full template)
                prompt = formatted_prompt
            
            prompt_source = "custom_template"
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
            logger.info(f"📝 PROMPT USED FOR NEW EMAIL:")
            logger.info(f"   Source: Custom prompt template (versioned endpoint)")
            logger.info(f"   Original Prompt Length: {len(prompt_template)} characters")
            logger.info(f"   Final Prompt Length: {len(prompt)} characters")
            logger.info(f"   Prompt Hash: {prompt_hash}")
            logger.info(f"   Merchant: {merchant_name}")
            logger.info(f"   Full Prompt Content:\n{'='*80}\n{prompt}\n{'='*80}")
        except KeyError as e:
            logger.warning(f"⚠️ Custom prompt template missing variable {e}, using default")
            prompt_template = None
    
    # If no custom template provided, try to get from environment variable
    if not prompt_template:
        env_prompt_template = os.getenv('NEW_EMAIL_PROMPT_TEMPLATE')
        if env_prompt_template:
            try:
                prompt = env_prompt_template.format(
                    AFFIRM_VOICE_GUIDELINES=AFFIRM_VOICE_GUIDELINES,
                    merchant_name=merchant_name,
                    contact_title_str=contact_title_str,
                    merchant_industry_str=merchant_industry_str,
                    merchant_website_str=merchant_website_str,
                    sender_name=sender_name,
                    account_description_str=account_description_str,
                    account_revenue_str=account_revenue_str,
                    account_gmv_str=account_gmv_str,
                    account_employees_str=account_employees_str,
                    account_location_str=account_location_str
                )
                prompt_source = "env_variable"
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
                logger.info(f"📝 PROMPT USED FOR NEW EMAIL:")
                logger.info(f"   Source: NEW_EMAIL_PROMPT_TEMPLATE environment variable")
                logger.info(f"   Endpoint: /api/workato/send-new-email (Default)")
                logger.info(f"   Prompt Type: new-email")
                logger.info(f"   Prompt Hash: {prompt_hash}")
                logger.info(f"   Prompt Length: {len(prompt)} characters")
                logger.info(f"   Merchant: {merchant_name}")
                logger.info(f"   Full Prompt Content:\n{'='*80}\n{prompt}\n{'='*80}")
            except KeyError as e:
                logger.warning(f"⚠️ NEW_EMAIL_PROMPT_TEMPLATE missing variable {e}, using default")
                prompt_template = None
    
    # Default prompt if no custom template or formatting failed
    if not prompt_template:
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
    
    # Log default prompt usage
    if prompt_source == "default":
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        logger.info(f"📝 PROMPT USED FOR NEW EMAIL:")
        logger.info(f"   Source: Default prompt template (hardcoded)")
        logger.info(f"   Endpoint: /api/workato/send-new-email (Default)")
        logger.info(f"   Prompt Type: new-email")
        logger.info(f"   Prompt Hash: {prompt_hash}")
        logger.info(f"   Prompt Length: {len(prompt)} characters")
        logger.info(f"   Merchant: {merchant_name}")
        logger.info(f"   Full Prompt Content:\n{'='*80}\n{prompt}\n{'='*80}")

    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        logger.info(f"🤖 Using OpenAI model: {OPENAI_MODEL}")
        logger.info(f"🤖 Generating new email message...")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )

        if response and response.choices:
            response_text = response.choices[0].message.content.strip()

            # Extract Subject Line and Email Body using regex
            subject_line_match = re.search(r"\*\*Subject Line:\*\*\s*(.*)", response_text)
            email_body_match = re.search(r"\*\*Email Body:\*\*\s*(.*)", response_text, re.DOTALL)

            subject_line = subject_line_match.group(1).strip() if subject_line_match else f"Ready to go live with Affirm?"
            email_body = email_body_match.group(1).strip() if email_body_match else f"Hi {merchant_name},\n\nI wanted to check in on your Affirm integration. You've completed the technical setup, and we're here to help you take the final step to go live.\n\nIf you have any questions or need support, feel free to reach out. We're here when you're ready.\n\nBest,\n{sender_name}"

            return subject_line, email_body

        else:
            return f"Ready to go live with Affirm?", f"Hi {merchant_name},\n\nI wanted to check in on your Affirm integration. You've completed the technical setup, and we're here to help you take the final step to go live.\n\nIf you have any questions or need support, feel free to reach out. We're here when you're ready.\n\nBest,\n{sender_name}"

        
    except Exception as e:
        logger.error(f"❌ Error generating AI response: {e}")
        return f"Ready to go live with Affirm?", f"Hi {merchant_name},\n\nI wanted to check in on your Affirm integration. You've completed the technical setup, and we're here to help you take the final step to go live.\n\nIf you have any questions or need support, feel free to reach out. We're here when you're ready.\n\nBest,\n{sender_name}"

def send_email(to_email, merchant_name, subject_line, email_content, campaign_name=None, base_url="https://web-production-6dfbd.up.railway.app", version_endpoint=None):
    """Send email with tracking - exact copy from 2025_hackathon.py."""
    try:
        from email_tracker import EmailTracker
        import time
        import random
        
        # Initialize email tracker
        tracker = EmailTracker()
        
        # Track the email and get tracking ID
        # Default to main endpoint if version_endpoint is not provided
        if not version_endpoint:
            version_endpoint = '/api/workato/send-new-email'
        
        logger.info(f"📧 Sending email to {to_email} with version_endpoint: {version_endpoint}")
        
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com'),
            subject=subject_line,
            campaign_name=campaign_name or "Personalized Outreach",
            version_endpoint=version_endpoint
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
        # Update status to 'Email Bounced' if tracking_id exists
        if tracking_id and DB_AVAILABLE:
            try:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE email_tracking 
                        SET status = 'Email Bounced'
                        WHERE tracking_id = %s
                    ''', (tracking_id,))
                    conn.commit()
                    conn.close()
                    logger.info(f"📧 Marked email as bounced: {tracking_id}")
            except Exception as db_error:
                logger.error(f"Error updating bounce status: {db_error}")
        
        return {
            'status': 'error',
            'error': str(e)
        }

def send_threaded_email_reply(to_email, subject, reply_content, original_message_id, sender_name, cc_recipients=None):
    """
    Send a threaded email reply that maintains the conversation thread.
    Uses SMTP like 2025_hackathon.py for better outbox visibility.
    Includes CC recipients from the original email if provided.
    """
    try:
        import smtplib
        import time
        import random
        from email_tracker import EmailTracker
        
        # Build recipient list (To + CC)
        all_recipients = [to_email]
        if cc_recipients:
            # cc_recipients can be a string (comma-separated) or a list
            if isinstance(cc_recipients, str):
                # Parse comma-separated string
                cc_list = [cc.strip() for cc in cc_recipients.split(',') if cc.strip()]
            else:
                cc_list = [cc.strip() for cc in cc_recipients if cc.strip()]
            all_recipients.extend(cc_list)
            logger.info(f"📧 Reply will include CC recipients: {', '.join(cc_list)}")
        
        logger.info(f"Preparing to send threaded reply to {to_email} with subject: {subject}")
        if cc_recipients:
            logger.info(f"📧 CC recipients: {cc_recipients}")
        
        # Initialize email tracker (same as 2025_hackathon.py)
        tracker = EmailTracker()
        
        # Track the email and get tracking ID
        # Use the reply-to-emails endpoint for version tracking
        version_endpoint = '/api/workato/reply-to-emails'
        logger.info(f"📧 Sending reply email to {to_email} with version_endpoint: {version_endpoint}")
        
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com'),
            subject=subject,
            campaign_name="AI Email Reply",
            version_endpoint=version_endpoint
        )
        
        # Add tracking pixel to email content
        tracked_email_content = tracker.add_tracking_to_email(reply_content, tracking_id, "https://web-production-6dfbd.up.railway.app")
        
        # Create email message with enhanced headers (same as 2025_hackathon.py)
        msg = MIMEMultipart()
        msg["From"] = f"Jake Morgan - Affirm <{os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com')}>"
        msg["To"] = to_email
        if cc_recipients:
            # Format CC header (can be string or list)
            if isinstance(cc_recipients, str):
                msg["Cc"] = cc_recipients
            else:
                msg["Cc"] = ", ".join(cc_recipients)
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
            if cc_recipients:
                # Format CC header for Gmail API
                if isinstance(cc_recipients, str):
                    message["cc"] = cc_recipients
                else:
                    message["cc"] = ", ".join(cc_recipients)
                logger.info(f"📧 Including CC recipients in reply: {message['cc']}")
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
            if cc_recipients:
                logger.info(f"📧 CC recipients: {cc_recipients}")
            logger.info(f"📧 Subject: {subject}")
            logger.info(f"📧 Message size: {len(raw_message)} characters")
            
            response = service.users().messages().send(userId='me', body=message_body).execute()
            logger.info("📧 Email sent successfully via Gmail API!")
            logger.info(f"📧 Gmail Message ID: {response.get('id')}")
            logger.info(f"📧 Thread ID: {response.get('threadId')}")
            logger.info(f"📧 Label IDs: {response.get('labelIds')}")
            
        except Exception as gmail_error:
            logger.error(f"❌ Gmail API Error: {gmail_error}")
            # Update status to 'Email Bounced' if tracking_id exists
            if tracking_id and DB_AVAILABLE:
                try:
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE email_tracking 
                            SET status = 'Email Bounced'
                            WHERE tracking_id = %s
                        ''', (tracking_id,))
                        conn.commit()
                        conn.close()
                        logger.info(f"📧 Marked threaded email as bounced due to Gmail API error: {tracking_id}")
                except Exception as db_error:
                    logger.error(f"Error updating bounce status: {db_error}")
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

    logger.info(f"🔍 Found {len(emails_needing_replies)} threads needing replies")
    
    # Deduplicate by threadId to ensure we only send ONE reply per Gmail thread
    # This handles cases where the same thread might appear multiple times
    seen_threads = {}
    unique_threads = []
    threads_without_id = []  # Track emails without threadId separately
    
    for email in emails_needing_replies:
        thread_id = email.get('threadId')
        email_id = email.get('id', 'unknown')
        sender = email.get('sender', 'unknown')
        
        if not thread_id:
            # If no threadId, use email ID as fallback for deduplication
            if email_id not in seen_threads:
                seen_threads[email_id] = email
                threads_without_id.append(email)
                logger.warning(f"⚠️ Email {email_id} from {sender} has no threadId - using email ID for deduplication")
            else:
                logger.info(f"⚠️ Skipping duplicate email {email_id} (no threadId) - already processing")
        elif thread_id not in seen_threads:
            seen_threads[thread_id] = email
            unique_threads.append(email)
            logger.info(f"✅ Added thread {thread_id} from {sender} (email {email_id}) to processing queue")
        else:
            logger.warning(f"⚠️ Skipping duplicate thread {thread_id} from {sender} (email {email_id}) - already processing")
            logger.warning(f"   First occurrence: {seen_threads[thread_id].get('id')} from {seen_threads[thread_id].get('sender')}")
    
    # Add emails without threadId to unique_threads (they'll be processed separately)
    unique_threads.extend(threads_without_id)
    
    logger.info(f"📧 Processing {len(unique_threads)} unique thread(s) that need replies...")
    logger.info(f"   - {len([t for t in unique_threads if t.get('threadId')])} with threadId")
    logger.info(f"   - {len(threads_without_id)} without threadId")
    
    # Process all unique threads that need replies
    processed_thread_ids = set()  # Track processed threads to prevent duplicates
    
    for i, email in enumerate(unique_threads):
        thread_id = email.get('threadId', 'No ID')
        email_id = email.get('id', 'unknown')
        sender = email.get('sender', 'unknown')
        logger.info(f"📧 Processing thread {i+1}/{len(unique_threads)}: threadId={thread_id}, emailId={email_id}, sender={sender}")
        
        # Double-check we haven't already processed this thread in this batch (safety check)
        if thread_id and thread_id != 'No ID':
            if thread_id in processed_thread_ids:
                logger.warning(f"⚠️ Thread {thread_id} already processed in this batch - skipping to prevent duplicate reply")
                continue
            processed_thread_ids.add(thread_id)
        
        # Extract contact information
        contact_name = email.get('contact_name', email['sender'].split("@")[0].capitalize())
        contact_email = email['sender']
        account_id = email.get('account_id')
        salesforce_id = email.get('salesforce_id')
        
        # Sender information (matching send_new_email)
        sender_name = "Jake Morgan"
        sender_title = "Business Development"
        
        # Build full conversation history from the thread
        try:
            creds = authenticate_gmail()
            service = build('gmail', 'v1', credentials=creds)
            
            # Get all messages in the thread to build full conversation history
            thread_data = service.users().threads().get(userId='me', id=thread_id).execute()
            thread_messages = thread_data.get('messages', [])
            
            # Build conversation history with all messages in chronological order
            conversation_parts = []
            cc_recipients = None  # Will store CC from the latest message that needs a reply
            
            for msg in thread_messages:
                try:
                    msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                    headers = msg_data['payload'].get('headers', [])
                    msg_sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                    msg_to = next((h['value'] for h in headers if h['name'] == 'To'), None)
                    msg_subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    msg_date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                    msg_body = extract_email_body(msg_data['payload'])
                    
                    # Get internal date for sorting
                    internal_date = msg_data.get('internalDate', 0)
                    
                    conversation_parts.append({
                        'sender': msg_sender,
                        'to': msg_to,
                        'subject': msg_subject,
                        'date': msg_date,
                        'body': msg_body,
                        'internal_date': int(internal_date) if internal_date else 0,
                        'cc': next((h['value'] for h in headers if h['name'] == 'Cc'), None),
                        'message_id': msg['id']
                    })
                except Exception as e:
                    logger.debug(f"Error extracting message {msg['id']} from thread: {e}")
                    continue
            
            # Sort by internal date to get chronological order
            conversation_parts.sort(key=lambda x: x['internal_date'])
            
            # Get participants from the LATEST message only (To + CC)
            # This ensures we only reply to people who were on the latest message
            cc_recipients = None
            jake_email = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com').lower()
            jake_email_normalized = normalize_email(jake_email)
            sender_email_normalized = normalize_email(contact_email)
            
            def extract_email_from_header(header_value):
                """Extract email address from header value (handles 'Name <email@domain.com>' format)."""
                if not header_value:
                    return None
                if '<' in header_value and '>' in header_value:
                    return header_value.split('<')[1].split('>')[0].strip().lower()
                return header_value.strip().lower()
            
            def parse_email_list(header_value):
                """Parse comma-separated email list and return list of clean email addresses."""
                if not header_value:
                    return []
                if isinstance(header_value, str):
                    email_list = [e.strip() for e in header_value.split(',') if e.strip()]
                else:
                    email_list = [e.strip() for e in header_value if e.strip()]
                
                clean_emails = []
                for email_str in email_list:
                    email_clean = extract_email_from_header(email_str)
                    if email_clean:
                        clean_emails.append(email_clean)
                return clean_emails
            
            if conversation_parts:
                latest_message = conversation_parts[-1]  # Last message is the latest
                
                # Get all recipients from latest message (To + CC)
                latest_to = latest_message.get('to')
                latest_cc = latest_message.get('cc')
                
                all_latest_recipients = set()
                
                # Add To recipients
                to_emails = parse_email_list(latest_to)
                for to_email_addr in to_emails:
                    if normalize_email(to_email_addr) != jake_email_normalized:
                        all_latest_recipients.add(to_email_addr)
                
                # Add CC recipients
                cc_emails = parse_email_list(latest_cc)
                for cc_email in cc_emails:
                    if normalize_email(cc_email) != jake_email_normalized:
                        all_latest_recipients.add(cc_email)
                
                # Remove the primary sender (they go in To, not CC)
                cc_recipients_list = [recipient_email for recipient_email in all_latest_recipients if normalize_email(recipient_email) != sender_email_normalized]
                
                if cc_recipients_list:
                    cc_recipients = ', '.join(sorted(cc_recipients_list))
                    logger.info(f"📧 Found {len(cc_recipients_list)} participants from latest message to CC: {cc_recipients}")
                else:
                    cc_recipients = None
                    logger.info(f"📧 No additional participants from latest message (only primary sender)")
            
            # Build conversation history string
            conversation_history_lines = []
            for i, msg_part in enumerate(conversation_parts, 1):
                conversation_history_lines.append(f"--- Message {i} ---")
                conversation_history_lines.append(f"From: {msg_part['sender']}")
                conversation_history_lines.append(f"Date: {msg_part['date']}")
                conversation_history_lines.append(f"Subject: {msg_part['subject']}")
                conversation_history_lines.append(f"Body:\n{msg_part['body']}")
                conversation_history_lines.append("")
            
            conversation_content = "\n".join(conversation_history_lines)
            logger.info(f"📧 Built conversation history with {len(conversation_parts)} messages for thread {thread_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not build full conversation history, using single email: {e}")
            # Fallback to single email if we can't get thread history
            conversation_content = f"📧 EMAIL TO RESPOND TO:\nSubject: {email['subject']}\nFrom: {email['sender']}\nBody: {email['body']}"
            cc_recipients = None  # Initialize if we couldn't get thread history
        
        # If we don't have conversation_content yet, set it
        if 'conversation_content' not in locals():
            conversation_content = f"📧 EMAIL TO RESPOND TO:\nSubject: {email['subject']}\nFrom: {email['sender']}\nBody: {email['body']}"
        
        # If we don't have cc_recipients yet, try to get it from the original email
        if not cc_recipients:
            try:
                creds = authenticate_gmail()
                service = build('gmail', 'v1', credentials=creds)
                original_msg_data = service.users().messages().get(userId='me', id=email['id']).execute()
                original_headers = original_msg_data['payload'].get('headers', [])
                original_cc = next((h['value'] for h in original_headers if h['name'] == 'Cc'), None)
                if original_cc:
                    cc_recipients = original_cc
                    logger.info(f"📧 Found CC recipients from original email: {cc_recipients}")
            except Exception as e:
                logger.debug(f"Could not extract CC from original email: {e}")
                cc_recipients = None
        
        try:
            # Generate AI response using the full conversation history
            logger.info(f"🤖 Generating AI response for thread {thread_id} from {contact_email}")
            ai_response = generate_ai_response(email['body'], sender_name, contact_name, conversation_content)
            logger.info(f"✅ AI response generated for thread {thread_id}")
            
            # Send threaded reply (include CC recipients if found)
            logger.info(f"📧 Sending reply email to {contact_email} for thread {thread_id}")
            email_result = send_threaded_email_reply(
                to_email=contact_email,
                subject=email['subject'],
                reply_content=ai_response,
                original_message_id=email['id'],
                sender_name=sender_name,
                cc_recipients=cc_recipients
            )
            
            email_status = email_result['status'] if isinstance(email_result, dict) else email_result
            tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""
            
            # Check if email was actually sent successfully
            if isinstance(email_result, dict) and email_result.get('status') == 'success':
                logger.info(f"✅ Successfully sent reply to thread {thread_id} from {contact_email}")
            else:
                logger.warning(f"⚠️ Reply email result for thread {thread_id}: {email_result}")
            
        except Exception as e:
            logger.error(f"❌ Error processing email from {contact_email} (thread {thread_id}): {e}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            email_status = f"❌ Failed to process email: {str(e)}"
            email_result = None
            tracking_info = ""
            ai_response = "<p>Sorry, I couldn't generate a response at this time.</p>"

        # Mark email as read (skip for now - function not implemented)
        # try:
        #     mark_emails_as_read([email['id']])
        # except Exception as e:
        #     logger.error(f"❌ Error marking email as read: {e}")

        # Determine if email was successfully sent
        was_sent = isinstance(email_result, dict) and email_result.get('status') == 'success'

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
            "emails_processed": 1,
            "reply_sent": was_sent
        })

    # Count successful replies sent
    replies_sent = sum(1 for r in responses if r.get('reply_sent', False))
    
    logger.info(f"📊 Summary: Processed {len(responses)} conversation threads, {replies_sent} replies successfully sent")
    if replies_sent < len(responses):
        logger.warning(f"⚠️ {len(responses) - replies_sent} threads processed but replies were not sent (check email_status in responses)")
    
    return {
        "status": "success",
        "message": f"Processed {len(responses)} conversation threads, {replies_sent} replies sent",
        "emails_processed": len(responses),
        "replies_sent": replies_sent,
        "responses": responses
    }

def get_emails_needing_replies_with_accounts(accounts):
    """Get emails needing replies using accounts provided by Workato instead of Salesforce query."""
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    logger.info("Connected to Gmail API")

    # Create a lookup dictionary for email addresses from Workato accounts
    # Store both original and normalized versions for matching
    account_emails = {}
    normalized_account_emails = {}  # Maps normalized email -> account info
    for account in accounts:
        email_addr = account.get('email', '').lower().strip()
        if email_addr:
            normalized = normalize_email(email_addr)
            account_emails[email_addr] = {
                'contact_id': account.get('contact_id'),
                'account_id': account.get('account_id'),
                'contact_name': account.get('name'),
                'normalized_email': normalized
            }
            # Store normalized version for alias matching
            normalized_account_emails[normalized] = account_emails[email_addr]

    logger.info(f"Processing {len(account_emails)} email addresses from Workato")
    logger.info(f"Normalized email lookup: {list(normalized_account_emails.keys())}")

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
        
        # Extract and normalize sender email address
        sender_email = normalize_email(sender)
        sender_email_original = sender.lower()
        if '<' in sender_email_original and '>' in sender_email_original:
            sender_email_original = sender_email_original.split('<')[1].split('>')[0]
        
        # Check if this email is from one of the Workato-provided accounts
        # Check both exact match and normalized match (for alias handling)
        account_info = None
        if sender_email_original in account_emails:
            account_info = account_emails[sender_email_original]
        elif sender_email in normalized_account_emails:
            account_info = normalized_account_emails[sender_email]
            logger.info(f"📧 Matched email alias: {sender_email_original} -> {sender_email} (normalized)")
        
        if account_info:
            # Get email body
            body = extract_email_body(message['payload'])
            
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
                'contact_id': account_info['contact_id'],
                'normalized_sender': sender_email  # Store normalized for thread matching
            }
            emails.append(email_data)
            logger.info(f"Found email from Workato account: {sender} (normalized: {sender_email}) - {subject}")

    logger.info(f"Found {len(emails)} emails from Workato-provided accounts")

    # Also check threads that contain emails from our accounts (even if latest email doesn't match)
    # This handles cases where original email was from alias, but reply is from base email
    thread_ids_from_emails = {email.get('threadId') for email in emails if email.get('threadId')}
    
    # Also find threads where Workato accounts appear in To or CC (not just From)
    # This allows us to reply to threads where the latest message is from a CC'd participant
    logger.info("🔍 Scanning inbox for threads where Workato accounts are recipients (To/CC)...")
    thread_ids_with_account_recipients = set()
    
    def extract_email_from_header(header_value):
        """Extract email address from header value (handles 'Name <email@domain.com>' format)."""
        if not header_value:
            return None
        if '<' in header_value and '>' in header_value:
            return header_value.split('<')[1].split('>')[0].strip().lower()
        return header_value.strip().lower()
    
    def parse_email_list(header_value):
        """Parse comma-separated email list and return list of clean email addresses."""
        if not header_value:
            return []
        if isinstance(header_value, str):
            email_list = [e.strip() for e in header_value.split(',') if e.strip()]
        else:
            email_list = [e.strip() for e in header_value if e.strip()]
        
        clean_emails = []
        for email_str in email_list:
            email_clean = extract_email_from_header(email_str)
            if email_clean:
                clean_emails.append(email_clean)
        return clean_emails
    
    # Scan all inbox messages to find threads where Workato accounts are in To/CC
    for msg in messages:
        try:
            msg_id = msg['id']
            message = service.users().messages().get(userId='me', id=msg_id).execute()
            thread_id = message.get('threadId')
            if not thread_id:
                continue
            
            headers = message['payload'].get('headers', [])
            to_header = next((h['value'] for h in headers if h['name'] == 'To'), '')
            cc_header = next((h['value'] for h in headers if h['name'] == 'Cc'), '')
            
            # Check if any Workato account is in To or CC
            to_emails = parse_email_list(to_header)
            cc_emails = parse_email_list(cc_header)
            all_recipients = set(to_emails + cc_emails)
            
            # Check if any recipient matches a Workato account
            for recipient in all_recipients:
                recipient_normalized = normalize_email(recipient)
                if recipient in account_emails or recipient_normalized in normalized_account_emails:
                    thread_ids_with_account_recipients.add(thread_id)
                    logger.info(f"📧 Found thread {thread_id} where Workato account {recipient} is a recipient")
                    break
        except Exception as e:
            logger.debug(f"Error checking message {msg.get('id', 'unknown')} for recipient match: {e}")
            continue
    
    # Combine thread IDs: those with emails from accounts + those with accounts as recipients
    all_relevant_thread_ids = thread_ids_from_emails | thread_ids_with_account_recipients
    logger.info(f"📊 Found {len(thread_ids_from_emails)} threads with emails from accounts, {len(thread_ids_with_account_recipients)} threads with accounts as recipients, {len(all_relevant_thread_ids)} total unique threads")
    
    # For each thread that has at least one email from our accounts OR has our accounts as recipients, check ALL messages in thread
    all_thread_emails = {}
    for thread_id in all_relevant_thread_ids:
        try:
            thread_data = service.users().threads().get(userId='me', id=thread_id).execute()
            thread_messages = thread_data.get('messages', [])
            
            for msg in thread_messages:
                msg_id = msg['id']
                message = service.users().messages().get(userId='me', id=msg_id).execute()
                
                headers = message['payload'].get('headers', [])
                sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                sender_normalized = normalize_email(sender)
                
                # Check if this message is from one of our accounts (exact or normalized)
                is_from_account = False
                account_info = None
                
                sender_original = sender.lower()
                if '<' in sender_original and '>' in sender_original:
                    sender_original = sender_original.split('<')[1].split('>')[0]
                
                if sender_original in account_emails:
                    account_info = account_emails[sender_original]
                    is_from_account = True
                elif sender_normalized in normalized_account_emails:
                    account_info = normalized_account_emails[sender_normalized]
                    is_from_account = True
                    logger.info(f"📧 Found alias match in thread {thread_id}: {sender_original} -> {sender_normalized}")
                
                if thread_id not in all_thread_emails:
                    all_thread_emails[thread_id] = []
                
                all_thread_emails[thread_id].append({
                    'id': msg_id,
                    'threadId': thread_id,
                    'sender': sender,
                    'subject': subject,
                    'date': date,
                    'body': extract_email_body(message['payload']),
                    'is_from_account': is_from_account,
                    'account_info': account_info,
                    'normalized_sender': sender_normalized
                })
        except Exception as e:
            logger.warning(f"⚠️ Error processing thread {thread_id}: {e}")
            # Fall back to emails we already found
            if thread_id not in all_thread_emails:
                all_thread_emails[thread_id] = []
    for email in emails:
                    if email.get('threadId') == thread_id:
                        email['is_from_account'] = True
                        all_thread_emails[thread_id].append(email)

    # Group emails by conversation thread (threadId)
    thread_emails = all_thread_emails
    
    emails_needing_replies = []
    
    # Check each conversation thread - reply if:
    # 1. Last message is from merchant (not from us), OR
    # 2. Last message is from a CC'd participant and a Workato account is involved in the thread
    for thread_id, emails_in_thread in thread_emails.items():
        # Sort emails by date to get the latest one
        emails_in_thread.sort(key=lambda x: x.get('date', ''), reverse=True)
        latest_email = emails_in_thread[0]  # Most recent email in this thread
        
        # Get full message data to check To/CC headers
        try:
            latest_msg_data = service.users().messages().get(userId='me', id=latest_email['id']).execute()
            latest_headers = latest_msg_data['payload'].get('headers', [])
            latest_to = next((h['value'] for h in latest_headers if h['name'] == 'To'), '')
            latest_cc = next((h['value'] for h in latest_headers if h['name'] == 'Cc'), '')
        except Exception as e:
            logger.warning(f"⚠️ Error getting headers for latest message in thread {thread_id}: {e}")
            latest_to = ''
            latest_cc = ''
        
        # Check if any Workato account is involved in this thread (in any message's To/CC)
        thread_has_account_recipient = thread_id in thread_ids_with_account_recipients
        
        # Check if latest sender was CC'd in a previous message (if thread has account recipient)
        latest_sender = latest_email.get('sender', '').lower()
        latest_sender_normalized = latest_email.get('normalized_sender') or normalize_email(latest_sender)
        latest_sender_original = latest_sender
        if '<' in latest_sender_original and '>' in latest_sender_original:
            latest_sender_original = latest_sender_original.split('<')[1].split('>')[0]
        
        # Check if latest sender was CC'd in any previous message in this thread
        latest_sender_was_ccd = False
        if thread_has_account_recipient:
            # Check all previous messages (not the latest) to see if latest sender was CC'd
            for prev_email in emails_in_thread[1:]:  # Skip latest email
                try:
                    prev_msg_data = service.users().messages().get(userId='me', id=prev_email['id']).execute()
                    prev_headers = prev_msg_data['payload'].get('headers', [])
                    prev_cc = next((h['value'] for h in prev_headers if h['name'] == 'Cc'), '')
                    prev_cc_emails = parse_email_list(prev_cc)
                    
                    # Check if latest sender was in CC of this previous message
                    for cc_email in prev_cc_emails:
                        cc_normalized = normalize_email(cc_email)
                        if (cc_email == latest_sender_original or 
                            cc_normalized == latest_sender_normalized or
                            latest_sender_original in cc_email or
                            latest_sender_normalized in cc_normalized):
                            latest_sender_was_ccd = True
                            logger.info(f"📧 Thread {thread_id}: Latest sender {latest_sender_original} was CC'd in previous message")
                            break
                    
                    if latest_sender_was_ccd:
                        break
                except Exception as e:
                    logger.debug(f"Error checking CC in previous message: {e}")
                    continue
        
        # Ensure latest_email has account_info if it's from one of our accounts
        if latest_email.get('account_info'):
            # Use the account_info from the email
            pass
        else:
            # Try to find account_info for this email
            if latest_sender_original in account_emails:
                latest_email['account_info'] = account_emails[latest_sender_original]
            elif latest_sender_normalized in normalized_account_emails:
                latest_email['account_info'] = normalized_account_emails[latest_sender_normalized]
        
        # Check if the latest message is from the merchant (not from us)
        is_from_merchant = False
        
        # Check if latest sender is one of our Workato accounts (merchant)
        # Check both exact match and normalized match
        if latest_sender_normalized in normalized_account_emails:
            is_from_merchant = True
        else:
            # Also check if any part of the sender string matches
            if latest_sender_original in account_emails:
                is_from_merchant = True
            else:
                for account_email, account_data in account_emails.items():
                    normalized_account = account_data.get('normalized_email', normalize_email(account_email))
                    if account_email in latest_sender or normalized_account == latest_sender_normalized:
                        is_from_merchant = True
                        break
        
        # Determine if we should reply:
        # 1. Latest message is from merchant, OR
        # 2. Latest message is from someone who was CC'd AND thread has a Workato account as recipient
        should_reply = is_from_merchant or (latest_sender_was_ccd and thread_has_account_recipient)
        
        # Only reply if:
        # 1. Latest message is from merchant OR from a CC'd participant (and thread has account recipient)
        # 2. Thread hasn't been replied to yet
        has_been_replied = has_been_replied_to(latest_email['id'], service)
        logger.info(f"🔍 Thread {thread_id} decision: is_from_merchant={is_from_merchant}, latest_sender_was_ccd={latest_sender_was_ccd}, thread_has_account_recipient={thread_has_account_recipient}, should_reply={should_reply}, has_been_replied={has_been_replied}, latest_sender={latest_sender_normalized}")
        
        if should_reply and not has_been_replied:
            # If latest sender is not a merchant, we need to find the account_info from the thread
            account_info = latest_email.get('account_info')
            
            # If we don't have account_info, try to find it from the thread (find first Workato account in thread)
            if not account_info and thread_has_account_recipient:
                # Find the first Workato account that appears in To/CC of any message in this thread
                for email_in_thread in emails_in_thread:
                    try:
                        msg_data = service.users().messages().get(userId='me', id=email_in_thread['id']).execute()
                        headers = msg_data['payload'].get('headers', [])
                        to_header = next((h['value'] for h in headers if h['name'] == 'To'), '')
                        cc_header = next((h['value'] for h in headers if h['name'] == 'Cc'), '')
                        
                        to_emails = parse_email_list(to_header)
                        cc_emails = parse_email_list(cc_header)
                        all_recipients = set(to_emails + cc_emails)
                        
                        # Find first Workato account in recipients
                        for recipient in all_recipients:
                            recipient_normalized = normalize_email(recipient)
                            if recipient in account_emails:
                                account_info = account_emails[recipient]
                                break
                            elif recipient_normalized in normalized_account_emails:
                                account_info = normalized_account_emails[recipient_normalized]
                                break
                        
                        if account_info:
                            break
                    except Exception as e:
                        logger.debug(f"Error finding account_info in thread: {e}")
                        continue
            
            # Ensure email has all required fields for reply processing
            if not account_info:
                logger.warning(f"⚠️ Thread {thread_id} needs reply but missing account_info, skipping")
                continue
            
            # Add account info to email for reply processing
            reply_email = {
                'id': latest_email['id'],
                'threadId': thread_id,
                'sender': latest_email['sender'],
                'subject': latest_email['subject'],
                'body': latest_email.get('body', ''),
                'date': latest_email.get('date', ''),
                'contact_name': account_info.get('contact_name', latest_email.get('sender', '').split('@')[0].capitalize()),
                'account_id': account_info.get('account_id'),
                'contact_id': account_info.get('contact_id')
            }
            emails_needing_replies.append(reply_email)
            if is_from_merchant:
                logger.info(f"Conversation thread {thread_id} from {latest_email['sender']} needs a reply (last message from merchant, normalized: {latest_sender_normalized})")
            else:
                logger.info(f"Conversation thread {thread_id} from {latest_email['sender']} needs a reply (last message from CC'd participant, normalized: {latest_sender_normalized})")
        else:
            if not should_reply:
                logger.info(f"Conversation thread {thread_id} - latest message doesn't require reply (is_from_merchant={is_from_merchant}, latest_sender_was_ccd={latest_sender_was_ccd}, thread_has_account_recipient={thread_has_account_recipient})")
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
            'workato_get_all_emails': 'GET/POST /api/workato/get-all-emails',
            'workato_get_all_email_opens': 'GET/POST /api/workato/get-all-email-opens',
            'workato_update_sfdc_task_id': 'POST /api/workato/update-sfdc-task-id',
            'prompts_ui': 'GET /prompts',
            'prompts_api': 'GET/POST /api/prompts'
        }
    })

@app.route('/prompts')
def prompts_ui():
    """Serve the prompts management UI."""
    import os
    from flask import send_from_directory
    
    # Try multiple possible paths
    possible_paths = [
        'templates/prompts.html',
        os.path.join(os.path.dirname(__file__), 'templates', 'prompts.html'),
        os.path.join(os.getcwd(), 'templates', 'prompts.html'),
        'prompts.html'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
            except Exception as e:
                logger.error(f"Error reading prompts.html from {path}: {e}")
                continue
    
    # If file not found, return embedded HTML
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mail Maestro - Prompt Management</title>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
    <style>
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
        }
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --primary-light: #818cf8;
            --success: #10b981;
            --success-dark: #059669;
            --warning: #f59e0b;
            --danger: #ef4444;
            --gray-50: #f9fafb;
            --gray-100: #f3f4f6;
            --gray-200: #e5e7eb;
            --gray-300: #d1d5db;
            --gray-600: #4b5563;
            --gray-700: #374151;
            --gray-800: #1f2937;
            --gray-900: #111827;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            line-height: 1.6;
        }
        
        .app-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }
        
        .header-bar {
            background: white;
            border-bottom: 1px solid #e5e7eb;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .header-title {
            font-size: 20px;
            font-weight: 600;
            color: #111827;
        }
        
        .header-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .icon-btn {
            width: 36px;
            height: 36px;
            border: none;
            background: transparent;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #6b7280;
            transition: all 0.2s;
        }
        
        .icon-btn:hover {
            background: #f3f4f6;
            color: #111827;
        }
        
        .main-layout {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        
        .sidebar {
            width: 280px;
            background: white;
            border-right: 1px solid #e5e7eb;
            overflow-y: auto;
            padding: 24px;
        }
        
        .sidebar-search {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 24px;
        }
        
        .sidebar-section {
            margin-bottom: 32px;
        }
        
        .sidebar-section-title {
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .prompt-type-item {
            display: flex;
            align-items: center;
            padding: 10px 12px;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 4px;
            transition: all 0.2s;
            color: #374151;
            font-size: 14px;
        }
        
        .prompt-type-item:hover {
            background: #f3f4f6;
        }
        
        .prompt-type-item.active {
            background: #eff6ff;
            color: #2563eb;
            font-weight: 500;
        }
        
        .prompt-type-item .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #10b981;
            margin-right: 12px;
        }
        
        .content-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background: #f9fafb;
        }
        
        .content-header {
            background: white;
            border-bottom: 1px solid #e5e7eb;
            padding: 20px 24px;
        }
        
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }
        
        .tab {
            padding: 8px 16px;
            border: none;
            background: transparent;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            color: #6b7280;
            transition: all 0.2s;
        }
        
        .tab:hover {
            background: #f3f4f6;
        }
        
        .tab.active {
            background: #eff6ff;
            color: #2563eb;
        }
        
        .tab-count {
            margin-left: 6px;
            color: #9ca3af;
        }
        
        .table-container {
            flex: 1;
            overflow-y: auto;
            background: white;
            margin: 0 24px 24px 24px;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
        }
        
        .table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .table thead {
            background: #f9fafb;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .table th {
            padding: 12px 16px;
            text-align: left;
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .table td {
            padding: 16px;
            border-bottom: 1px solid #f3f4f6;
            font-size: 14px;
            color: #374151;
        }
        
        .table tbody tr:hover {
            background: #f9fafb;
        }
        
        .table tbody tr:last-child td {
            border-bottom: none;
        }
        
        .prompt-variant-name {
            font-weight: 500;
            color: #111827;
            margin-bottom: 4px;
        }
        
        .prompt-preview {
            color: #6b7280;
            font-size: 13px;
            max-width: 500px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-active {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-draft {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-archived {
            background: #f3f4f6;
            color: #6b7280;
        }
        
        .edit-btn {
            padding: 6px 12px;
            background: #eff6ff;
            color: #2563eb;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .edit-btn:hover {
            background: #dbeafe;
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 800px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
        }
        
        .modal-header {
            padding: 20px 24px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-title {
            font-size: 18px;
            font-weight: 600;
            color: #111827;
        }
        
        .modal-close {
            width: 32px;
            height: 32px;
            border: none;
            background: transparent;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #6b7280;
        }
        
        .modal-close:hover {
            background: #f3f4f6;
        }
        
        .modal-body {
            padding: 24px;
            overflow-y: auto;
            flex: 1;
        }
        
        .modal-textarea {
            width: 100%;
            min-height: 400px;
            padding: 16px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            font-family: 'SF Mono', 'Monaco', 'Menlo', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
            resize: vertical;
        }
        
        .modal-footer {
            padding: 16px 24px;
            border-top: 1px solid #e5e7eb;
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }
        
        .btn-primary {
            padding: 10px 20px;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
        }
        
        .btn-secondary {
            padding: 10px 20px;
            background: #f3f4f6;
            color: #374151;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 50px 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        
        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            animation: pulse 8s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.1); opacity: 0.8; }
        }
        
        .header h1 { 
            font-size: 3em; 
            margin-bottom: 12px; 
            font-weight: 700;
            letter-spacing: -0.02em;
            position: relative;
            z-index: 1;
        }
        
        .header p { 
            opacity: 0.95; 
            font-size: 1.2em; 
            font-weight: 400;
            position: relative;
            z-index: 1;
        }
        
        .content { 
            padding: 40px; 
            background: var(--gray-50);
        }
        
        .info-box {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
            border: none;
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 32px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            border-left: 4px solid var(--primary);
        }
        
        .info-box p { 
            color: var(--gray-800); 
            line-height: 1.7;
            font-size: 0.95em;
        }
        
        .prompt-card {
            background: white;
            border-radius: 20px;
            padding: 32px;
            margin-bottom: 32px;
            border: 1px solid var(--gray-200);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        
        .prompt-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: linear-gradient(180deg, var(--primary) 0%, var(--primary-light) 100%);
            transition: width 0.3s ease;
        }
        
        .prompt-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }
        
        .prompt-card:hover::before {
            width: 6px;
        }
        
        .prompt-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            gap: 20px;
        }
        
        .prompt-title { 
            font-size: 1.75em; 
            font-weight: 700; 
            color: var(--gray-900);
            letter-spacing: -0.01em;
            margin-bottom: 8px;
        }
        
        .prompt-description { 
            color: var(--gray-600); 
            font-size: 0.95em;
            line-height: 1.6;
        }
        
        .endpoint-badge {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 600;
            white-space: nowrap;
            box-shadow: 0 2px 4px rgba(99, 102, 241, 0.3);
            letter-spacing: 0.01em;
        }
        
        textarea {
            width: 100%;
            min-height: 320px;
            padding: 20px;
            border: 2px solid var(--gray-200);
            border-radius: 12px;
            font-family: 'SF Mono', 'Monaco', 'Menlo', 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.7;
            resize: vertical;
            transition: all 0.3s ease;
            background: var(--gray-50);
            color: var(--gray-900);
        }
        
        textarea:focus { 
            outline: none; 
            border-color: var(--primary);
            background: white;
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
        }
        
        .button-group { 
            display: flex; 
            gap: 12px; 
            margin-top: 20px;
            flex-wrap: wrap;
        }
        
        button {
            padding: 14px 28px;
            border: none;
            border-radius: 12px;
            font-size: 0.95em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            letter-spacing: 0.01em;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        button::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.3);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }
        
        button:active::before {
            width: 300px;
            height: 300px;
        }
        
        .btn-save { 
            background: linear-gradient(135deg, var(--success) 0%, var(--success-dark) 100%);
            color: white;
        }
        
        .btn-save:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(16, 185, 129, 0.3);
        }
        
        .btn-save:active {
            transform: translateY(0);
        }
        
        .btn-reset { 
            background: linear-gradient(135deg, var(--gray-600) 0%, var(--gray-700) 100%);
            color: white;
        }
        
        .btn-reset:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(75, 85, 99, 0.3);
        }
        
        .btn-reset:active {
            transform: translateY(0);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .status-message {
            padding: 16px 20px;
            border-radius: 12px;
            margin-top: 16px;
            display: none;
            font-weight: 500;
            animation: slideIn 0.3s ease-out;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(-10px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        
        .status-success { 
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            color: #065f46; 
            border: 1px solid #6ee7b7;
        }
        
        .status-error { 
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            color: #991b1b; 
            border: 1px solid #fca5a5;
        }
        
        @media (max-width: 768px) {
            .header h1 { font-size: 2em; }
            .header p { font-size: 1em; }
            .content { padding: 24px; }
            .prompt-card { padding: 24px; }
            .prompt-header { flex-direction: column; }
            .endpoint-badge { align-self: flex-start; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="header-bar">
            <div class="header-left">
                <div class="header-title" style="font-weight: 700; font-size: 18px; color: #111827; margin-right: 8px;">Mail Maestro</div>
                <div style="color: #6b7280; font-size: 20px; margin: 0 8px;">/</div>
                <div class="header-title">Prompts</div>
            </div>
            <div class="header-actions">
                <button class="icon-btn" title="Download">⬇</button>
                <button class="icon-btn" title="Settings">⚙</button>
            </div>
        </div>
        
        <div class="main-layout">
            <div class="sidebar">
                <input type="text" class="sidebar-search" placeholder="Search...">
                
                <div class="sidebar-section">
                    <div class="sidebar-section-title">Prompt Types</div>
                    <div class="prompt-type-item active" onclick="selectPromptType('new-email', event)">
                        <span class="dot"></span>
                        New Email Prompts
                    </div>
                    <div class="prompt-type-item" onclick="selectPromptType('reply-email', event)">
                        <span class="dot"></span>
                        Reply Email Prompts
                    </div>
                    <div class="prompt-type-item" onclick="selectPromptType('non-campaign-email', event)">
                        <span class="dot"></span>
                        Non-Campaign Email Prompts
                    </div>
                    <div class="prompt-type-item" onclick="selectPromptType('voice-guidelines', event)">
                        <span class="dot"></span>
                        Voice Guidelines
                    </div>
                </div>
                
                <div class="sidebar-section">
                    <div class="sidebar-section-title">Testing</div>
                    <div class="prompt-type-item" onclick="selectPromptType('test-merchant', event)">
                        <span class="dot"></span>
                        Test Merchant
                    </div>
                </div>
            </div>
            
            <div class="content-area">
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <div class="tabs">
                            <button class="tab active" onclick="selectTab('all', event)">
                                All prompts <span class="tab-count" id="all-count">3</span>
                            </button>
                            <button class="tab" onclick="selectTab('active', event)">
                                Active <span class="tab-count" id="active-count">2</span>
                            </button>
                            <button class="tab" onclick="selectTab('draft', event)">
                                Draft <span class="tab-count" id="draft-count">1</span>
                            </button>
                        </div>
                        <button class="btn-primary" onclick="createNewVersion()" style="margin-left: auto;">+ Create Version</button>
                    </div>
                </div>
                
                <div style="display: flex; gap: 24px; flex: 1; overflow: hidden;">
                    <div class="table-container" style="flex: 1;">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th style="width: 40px;"><input type="checkbox"></th>
                                    <th style="width: 60px;">#</th>
                                    <th>Version Name / Preview</th>
                                    <th style="width: 120px;">Status</th>
                                    <th style="width: 150px;">Endpoint</th>
                                    <th style="width: 120px;">Open Rate</th>
                                    <th style="width: 100px;">Actions</th>
                                    <th style="width: 100px;">Test</th>
                                    <th style="width: 100px;">Delete</th>
                                </tr>
                            </thead>
                            <tbody id="prompts-table-body">
                                <!-- Table rows will be populated by JavaScript -->
                            </tbody>
                        </table>
                    </div>
                    
                    <!-- Test Results Panel -->
                    <div id="test-results-panel" style="display: none; width: 400px; background: white; border-left: 1px solid #e5e7eb; padding: 24px; overflow-y: auto;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                            <h3 style="margin: 0; font-size: 18px; font-weight: 600;">Test Results</h3>
                            <button onclick="closeTestPanel()" style="background: transparent; border: none; font-size: 20px; cursor: pointer; color: #6b7280; padding: 4px 8px;">✕</button>
                        </div>
                        
                        <!-- Reply Input Section (only for reply-email prompts) -->
                        <div id="test-reply-input-section" style="display: none; margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151; font-size: 14px;">Message to Reply To:</label>
                            <textarea id="test-reply-input" rows="6" style="width: 100%; padding: 12px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical;" placeholder="Enter the message you want the AI to reply to..."></textarea>
                            <button onclick="generateTestReply()" class="btn-primary" style="width: 100%; margin-top: 12px;">Generate Reply</button>
                        </div>
                        
                        <div id="test-results-content" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; font-size: 14px; line-height: 1.6; background: #f9fafb; padding: 16px; border-radius: 8px; border: 1px solid #e5e7eb; min-height: 200px; overflow-y: auto; max-height: 600px;">
                            Click "Test" on any prompt to see results here.
                        </div>
                    </div>
                </div>
                
                <!-- Test Merchant Content -->
                <div class="content-area" id="test-merchant-content" style="display: none;">
                    <div class="content-header">
                        <h2 style="margin: 0 0 24px 0; font-size: 24px; font-weight: 600;">Test Merchant</h2>
                        <p style="color: #6b7280; margin-bottom: 24px;">Enter merchant information to test prompt responses</p>
                    </div>
                    
                    <div style="padding: 24px; max-width: 1200px;">
                        <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <h3 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 600;">Merchant Information</h3>
                            <form id="test-merchant-form" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;">
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Merchant Name *</label>
                                    <input type="text" id="merchant_name" name="merchant_name" required 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="Acme Corporation">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Contact Email</label>
                                    <input type="email" id="contact_email" name="contact_email" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="contact@acme.com">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Contact Title</label>
                                    <input type="text" id="contact_title" name="contact_title" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="CEO">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Industry</label>
                                    <input type="text" id="merchant_industry" name="merchant_industry" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="E-commerce">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Website</label>
                                    <input type="url" id="merchant_website" name="merchant_website" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="https://acme.com">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Location</label>
                                    <input type="text" id="account_location" name="account_location" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="San Francisco, CA">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Annual Revenue ($)</label>
                                    <input type="number" id="account_revenue" name="account_revenue" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="1000000">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Employees</label>
                                    <input type="number" id="account_employees" name="account_employees" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="50">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">GMV ($)</label>
                                    <input type="number" id="account_gmv" name="account_gmv" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="5000000">
                                </div>
                                <div>
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Last Activity</label>
                                    <input type="text" id="last_activity" name="last_activity" 
                                           style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;" 
                                           placeholder="Recent" value="Recent">
                                </div>
                                <div style="grid-column: 1 / -1;">
                                    <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Account Description</label>
                                    <textarea id="account_description" name="account_description" rows="3" 
                                              style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; font-family: inherit;" 
                                              placeholder="A leading e-commerce platform..."></textarea>
                                </div>
                                <div style="grid-column: 1 / -1; display: flex; gap: 12px; margin-top: 8px;">
                                    <button type="button" onclick="saveTestMerchant()" class="btn-primary" style="flex: 0 0 auto;">Save Test Merchant</button>
                                    <button type="button" onclick="loadTestMerchant()" class="btn-secondary" style="flex: 0 0 auto;">Load Saved</button>
                                </div>
                            </form>
                        </div>
                        
                        <div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <h3 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 600;">Generate Sample Response</h3>
                            <div style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Prompt Type</label>
                                <select id="sample-prompt-type" style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px;">
                                    <option value="new-email">New Email</option>
                                    <option value="reply-email">Reply Email</option>
                                </select>
                            </div>
                            <div id="conversation-context-section" style="margin-bottom: 20px; display: none;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Conversation Context (for reply emails)</label>
                                <textarea id="conversation_context" rows="4" 
                                          style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; font-family: inherit;" 
                                          placeholder="Previous conversation history..."></textarea>
                            </div>
                            <div style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">Use Custom Prompt (optional - leave empty to use default/current prompt)</label>
                                <textarea id="custom-prompt-content" rows="6" 
                                          style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; font-family: 'Courier New', monospace;" 
                                          placeholder="Leave empty to use the current prompt version, or paste a custom prompt template here..."></textarea>
                            </div>
                            <button type="button" onclick="generateSample()" class="btn-primary" style="width: 100%;">Generate Sample Response</button>
                            
                            <div id="sample-results" style="margin-top: 24px; display: none;">
                                <h4 style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600;">Generated Response</h4>
                                <div id="sample-output" style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; white-space: pre-wrap; font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.6;"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Edit Modal -->
    <div class="modal" id="edit-modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modal-title">Edit Prompt</div>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <div class="modal-body">
                <textarea class="modal-textarea" id="modal-textarea" placeholder="Enter prompt content..."></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn-primary" onclick="savePromptFromModal()">Save</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentPromptType = 'new-email';
        let currentTab = 'all';
        let promptsData = {
            'new-email': [],
            'reply-email': [],
            'voice-guidelines': []
        };
        let currentEditingPrompt = null;
        let variantStats = {};
        
        const promptTypes = {
            'new-email': {
                name: 'New Email Prompts',
                endpoint: '/api/workato/send-new-email',
                key: 'NEW_EMAIL_PROMPT_TEMPLATE'
            },
            'reply-email': {
                name: 'Reply Email Prompts',
                endpoint: '/api/workato/reply-to-emails',
                key: 'REPLY_EMAIL_PROMPT_TEMPLATE'
            },
            'voice-guidelines': {
                name: 'Voice Guidelines',
                endpoint: 'Global',
                key: 'AFFIRM_VOICE_GUIDELINES'
            }
        };
        
        async function loadStats() {
            try {
                const response = await fetch('/api/prompts/get-stats');
                const data = await response.json();
                console.log('Stats API response:', data);
                if (data.status === 'success') {
                    variantStats = data.stats || {};
                    console.log('Stats loaded into variantStats:', variantStats);
                } else {
                    console.error('Stats API returned error:', data);
                    variantStats = {};
                }
            } catch (error) {
                console.error('Error loading stats:', error);
                variantStats = {};
            }
        }
        
        window.addEventListener('DOMContentLoaded', async () => {
            console.log('Loading prompts and stats...');
            await Promise.all([loadAllPrompts(), loadStats()]);
            console.log('Prompts loaded:', promptsData);
            console.log('Stats loaded:', variantStats);
            renderTable();
        });
        
        function selectPromptType(type, event) {
            currentPromptType = type;
            document.querySelectorAll('.prompt-type-item').forEach(item => {
                item.classList.remove('active');
            });
            if (event && event.currentTarget) {
                event.currentTarget.classList.add('active');
            } else {
                // Fallback: find the clicked element by type
                document.querySelectorAll('.prompt-type-item').forEach(item => {
                    if (item.getAttribute('onclick') && item.getAttribute('onclick').includes(`'${type}'`)) {
                        item.classList.add('active');
                    }
                });
            }
            
            // Close test panel when switching prompts
            const testPanel = document.getElementById('test-results-panel');
            if (testPanel) {
                testPanel.style.display = 'none';
            }
            
            // Show/hide content areas
            const tableContainer = document.querySelector('div[style*="display: flex"][style*="gap: 24px"]') || 
                                   document.querySelector('.table-container')?.parentElement ||
                                   document.querySelector('div[style*="flex: 1"]');
            const testMerchantContent = document.getElementById('test-merchant-content');
            
            console.log('Switching to prompt type:', type);
            console.log('Table container found:', !!tableContainer);
            console.log('Test merchant content found:', !!testMerchantContent);
            
            if (type === 'test-merchant') {
                if (tableContainer) {
                    tableContainer.style.display = 'none';
                    console.log('Hiding table container');
                }
                if (testMerchantContent) {
                    testMerchantContent.style.display = 'block';
                    console.log('Showing test merchant content');
                    loadTestMerchant();
                }
            } else {
                if (tableContainer) {
                    tableContainer.style.display = 'flex';
                    console.log('Showing table container');
                }
                if (testMerchantContent) {
                    testMerchantContent.style.display = 'none';
                    console.log('Hiding test merchant content');
                }
                
                // Always reload prompts when switching types
                console.log('Loading prompts for type:', type);
                Promise.all([loadAllPrompts(), loadStats()]).then(() => {
                    console.log('Reloaded prompts and stats for type:', type);
                    console.log('Prompts for', type, ':', promptsData[type]);
                    renderTable();
                }).catch(error => {
                    console.error('Error reloading prompts:', error);
                    renderTable(); // Still try to render with existing data
                });
            }
        }
        
        function selectTab(tab, event) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            if (event && event.currentTarget) {
                event.currentTarget.classList.add('active');
            } else {
                // Fallback: find the clicked element
                document.querySelectorAll('.tab').forEach(t => {
                    if (t.getAttribute('onclick') && t.getAttribute('onclick').includes(`'${tab}'`)) {
                        t.classList.add('active');
                    }
                });
            }
            renderTable();
        }
        
        async function loadAllPrompts() {
            try {
                console.log('Loading prompts from API...');
                const [promptsResponse, versionsResponse] = await Promise.all([
                    fetch('/api/prompts/get'),
                    fetch('/api/prompts/get-versions')
                ]);
                
                if (!promptsResponse.ok) {
                    console.error('Failed to fetch prompts:', promptsResponse.status, promptsResponse.statusText);
                }
                
                const promptsData_result = await promptsResponse.json();
                console.log('Prompts API response:', promptsData_result);
                
                let versionsData = { status: 'success', versions: [] };
                
                try {
                    if (versionsResponse.ok) {
                        versionsData = await versionsResponse.json();
                        console.log('Versions API response:', versionsData);
                    }
                } catch (e) {
                    console.warn('Could not load versions:', e);
                }
                
                if (promptsData_result.status === 'success') {
                    // Start with default versions
                    promptsData = {
                        'new-email': [
                            { id: 1, name: 'Default Version', preview: (promptsData_result.prompts.new_email_prompt || '').substring(0, 100) || 'Default new email prompt template...', status: 'active', endpoint: '/api/workato/send-new-email', key: 'NEW_EMAIL_PROMPT_TEMPLATE', content: promptsData_result.prompts.new_email_prompt || '', version_letter: null }
                        ],
                        'reply-email': [
                            { id: 1, name: 'Default Version', preview: (promptsData_result.prompts.reply_email_prompt || '').substring(0, 100) || 'Default reply email prompt template...', status: 'active', endpoint: '/api/workato/reply-to-emails', key: 'REPLY_EMAIL_PROMPT_TEMPLATE', content: promptsData_result.prompts.reply_email_prompt || '', version_letter: null }
                        ],
                        'non-campaign-email': [
                            { id: 1, name: 'Default Version', preview: (promptsData_result.prompts.non_campaign_email_prompt || '').substring(0, 100) || 'Default non-campaign email prompt template...', status: 'active', endpoint: '/api/workato/check-non-campaign-emails', key: 'NON_CAMPAIGN_EMAIL_PROMPT_TEMPLATE', content: promptsData_result.prompts.non_campaign_email_prompt || '', version_letter: null }
                        ],
                        'voice-guidelines': [
                            { id: 1, name: 'Default Guidelines', preview: (promptsData_result.prompts.voice_guidelines || '').substring(0, 100) || 'Default voice guidelines...', status: 'active', endpoint: 'Global', key: 'AFFIRM_VOICE_GUIDELINES', content: promptsData_result.prompts.voice_guidelines || '', version_letter: null }
                        ]
                    };
                    
                    // Add versions from database
                    if (versionsData.status === 'success' && versionsData.versions && Array.isArray(versionsData.versions)) {
                        versionsData.versions.forEach((version, idx) => {
                            const versionId = 1000 + version.id; // Use high IDs for versions
                            const versionData = {
                                id: versionId,
                                name: version.version_name,
                                preview: (version.prompt_content || '').substring(0, 100) || 'No preview...',
                                status: version.status || 'draft',
                                endpoint: version.endpoint_path,
                                key: `${version.prompt_type.toUpperCase().replace('-', '_')}_PROMPT_TEMPLATE_${version.version_letter}`,
                                content: version.prompt_content || '',
                                version_letter: version.version_letter
                            };
                            
                            if (version.prompt_type === 'new-email') {
                                promptsData['new-email'].push(versionData);
                            } else if (version.prompt_type === 'reply-email') {
                                promptsData['reply-email'].push(versionData);
                            } else if (version.prompt_type === 'non-campaign-email') {
                                promptsData['non-campaign-email'].push(versionData);
                            }
                        });
                    }
                    
                    console.log('Loaded prompts data:', promptsData);
                } else {
                    console.error('Failed to load prompts:', promptsData_result);
                    // Initialize with empty data structure
                    promptsData = {
                        'new-email': [],
                        'reply-email': [],
                        'non-campaign-email': [],
                        'voice-guidelines': []
                    };
                }
            } catch (error) {
                console.error('Error loading prompts:', error);
                // Initialize with empty data structure on error
                promptsData = {
                    'new-email': [],
                    'reply-email': [],
                    'non-campaign-email': [],
                    'voice-guidelines': []
                };
            }
        }
        
        function renderTable() {
            const tbody = document.getElementById('prompts-table-body');
            if (!tbody) {
                console.error('Table body not found!');
                return;
            }
            
            const prompts = promptsData[currentPromptType] || [];
            console.log('Rendering table for type:', currentPromptType, 'with', prompts.length, 'prompts');
            console.log('Prompts data:', prompts);
            
            const filtered = currentTab === 'all' ? prompts : prompts.filter(p => p.status === currentTab);
            
            if (filtered.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="9" style="text-align: center; padding: 40px; color: #6b7280;">
                            No prompts found. ${prompts.length === 0 ? 'Click "+ Create Version" to create your first prompt version.' : 'Try selecting a different tab.'}
                        </td>
                    </tr>
                `;
            } else {
                tbody.innerHTML = filtered.map((prompt, index) => {
                    const endpoint = (prompt.endpoint || '/api/workato/send-new-email').trim();
                    console.log(`Looking up stats for endpoint: "${endpoint}"`);
                    console.log(`Available stats keys:`, Object.keys(variantStats));
                    const stats = variantStats[endpoint] || { total_sent: 0, total_opened: 0, open_rate: 0 };
                    const openRate = stats.open_rate || 0;
                    const totalSent = stats.total_sent || 0;
                    const totalOpened = stats.total_opened || 0;
                    console.log(`Stats for "${endpoint}":`, stats);
                    
                    return `
                    <tr>
                        <td><input type="checkbox"></td>
                        <td>${String(index + 1).padStart(2, '0')}</td>
                        <td>
                            <div class="prompt-variant-name">${prompt.name || 'Unnamed'}</div>
                            <div class="prompt-preview">${prompt.preview || 'No preview available'}...</div>
                        </td>
                        <td>
                            <span class="status-badge status-${prompt.status || 'draft'}">${(prompt.status || 'draft').charAt(0).toUpperCase() + (prompt.status || 'draft').slice(1)}</span>
                        </td>
                        <td>${prompt.endpoint || 'N/A'}</td>
                        <td style="text-align: right;">
                            <div style="font-weight: 600; color: #111827;">${openRate.toFixed(1)}%</div>
                            <div style="font-size: 12px; color: #6b7280;">${totalOpened}/${totalSent} opened</div>
                        </td>
                        <td>
                            <button class="edit-btn" onclick="openEditModal(${prompt.id})">Edit</button>
                        </td>
                        <td>
                            <button class="edit-btn" onclick="testPrompt(${prompt.id})" style="background: #f0fdf4; color: #166534;">Test</button>
                        </td>
                        <td>
                            ${prompt.version_letter ? `<button class="edit-btn" onclick="deletePrompt(${prompt.id})" style="background: #fef2f2; color: #991b1b;">Delete</button>` : '<span style="color: #9ca3af; font-size: 12px;">N/A</span>'}
                        </td>
                    </tr>
                `;
                }).join('');
            }
            
            // Update counts
            const allCount = prompts.length;
            const activeCount = prompts.filter(p => p.status === 'active').length;
            const draftCount = prompts.filter(p => p.status === 'draft').length;
            
            document.getElementById('all-count').textContent = allCount;
            document.getElementById('active-count').textContent = activeCount;
            document.getElementById('draft-count').textContent = draftCount;
        }
        
        function openEditModal(promptId) {
            const prompts = promptsData[currentPromptType] || [];
            const prompt = prompts.find(p => p.id === promptId);
            if (!prompt) return;
            
            currentEditingPrompt = prompt;
            document.getElementById('modal-title').textContent = `Edit: ${prompt.name}`;
            document.getElementById('modal-textarea').value = prompt.content || '';
            document.getElementById('edit-modal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('edit-modal').classList.remove('active');
            currentEditingPrompt = null;
        }
        
        async function savePromptFromModal() {
            if (!currentEditingPrompt) return;
            
            const content = document.getElementById('modal-textarea').value.trim();
            if (!content) {
                alert('Prompt cannot be empty');
                return;
            }
            
            try {
                // If it's a version (has version_letter), update via version endpoint
                if (currentEditingPrompt.version_letter) {
                    // Extract the real version ID from the database
                    // The prompt.id is 1000 + version.id, so we need to extract the real version ID
                    const versionId = currentEditingPrompt.id - 1000;
                    
                    const response = await fetch('/api/prompts/update-version', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            version_id: versionId,
                            prompt_content: content 
                        })
                    });
                    
                    const data = await response.json();
                    if (data.status === 'success') {
                        currentEditingPrompt.content = content;
                        currentEditingPrompt.preview = content.substring(0, 100);
                        await Promise.all([loadAllPrompts(), loadStats()]);
                        renderTable();
                        closeModal();
                        alert('✅ Version prompt saved successfully!');
                    } else {
                        alert('❌ Error: ' + data.message);
                    }
                    return;
                }
                
                const response = await fetch('/api/prompts/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: currentEditingPrompt.key, value: content })
                });
                
                const data = await response.json();
                if (data.status === 'success') {
                    // Reload prompts from database to ensure sync
                    await Promise.all([loadAllPrompts(), loadStats()]);
                    renderTable();
                    closeModal();
                    alert('✅ Prompt saved successfully!');
                } else {
                    alert('❌ Error: ' + data.message);
                }
            } catch (error) {
                alert('❌ Error saving prompt: ' + error.message);
            }
        }
        
        async function createNewVersion() {
            if (currentPromptType === 'voice-guidelines') {
                alert('Cannot create versions for voice guidelines');
                return;
            }
            
            const versionName = prompt('Enter version name:');
            if (!versionName) return;
            
            const promptContent = prompt('Enter prompt content (or leave empty to edit later):');
            
            try {
                const response = await fetch('/api/prompts/create-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        version_name: versionName,
                        prompt_type: currentPromptType,
                        prompt_content: promptContent || 'Enter your prompt here...'
                    })
                });
                
                const data = await response.json();
                if (data.status === 'success') {
                    alert(`✅ Version created! Endpoint: ${data.endpoint_path}`);
                    await Promise.all([loadAllPrompts(), loadStats()]);
                    renderTable();
                } else {
                    alert('❌ Error: ' + data.message);
                }
            } catch (error) {
                alert('❌ Error creating version: ' + error.message);
            }
        }
        
        // Close modal on outside click
        document.getElementById('edit-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'edit-modal') {
                closeModal();
            }
        });
        
        // Test Merchant Functions
        async function saveTestMerchant() {
            const form = document.getElementById('test-merchant-form');
            const formData = {
                merchant_name: document.getElementById('merchant_name').value,
                contact_email: document.getElementById('contact_email').value,
                contact_title: document.getElementById('contact_title').value,
                merchant_industry: document.getElementById('merchant_industry').value,
                merchant_website: document.getElementById('merchant_website').value,
                account_description: document.getElementById('account_description').value,
                account_revenue: parseFloat(document.getElementById('account_revenue').value) || 0,
                account_employees: parseInt(document.getElementById('account_employees').value) || 0,
                account_location: document.getElementById('account_location').value,
                account_gmv: parseFloat(document.getElementById('account_gmv').value) || 0,
                last_activity: document.getElementById('last_activity').value || 'Recent'
            };
            
            if (!formData.merchant_name) {
                alert('Please enter a merchant name');
                return;
            }
            
            try {
                const response = await fetch('/api/test-merchants/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                
                const data = await response.json();
                if (data.status === 'success') {
                    alert('✅ Test merchant saved successfully!');
                } else {
                    alert('❌ Error: ' + data.message);
                }
            } catch (error) {
                alert('❌ Error saving test merchant: ' + error.message);
            }
        }
        
        async function loadTestMerchant() {
            try {
                const response = await fetch('/api/test-merchants/get');
                const data = await response.json();
                
                if (data.status === 'success' && data.merchant) {
                    const m = data.merchant;
                    document.getElementById('merchant_name').value = m.merchant_name || '';
                    document.getElementById('contact_email').value = m.contact_email || '';
                    document.getElementById('contact_title').value = m.contact_title || '';
                    document.getElementById('merchant_industry').value = m.merchant_industry || '';
                    document.getElementById('merchant_website').value = m.merchant_website || '';
                    document.getElementById('account_description').value = m.account_description || '';
                    document.getElementById('account_revenue').value = m.account_revenue || '';
                    document.getElementById('account_employees').value = m.account_employees || '';
                    document.getElementById('account_location').value = m.account_location || '';
                    document.getElementById('account_gmv').value = m.account_gmv || '';
                    document.getElementById('last_activity').value = m.last_activity || 'Recent';
                }
            } catch (error) {
                console.error('Error loading test merchant:', error);
            }
        }
        
        async function generateSample() {
            const promptType = document.getElementById('sample-prompt-type').value;
            const conversationContext = document.getElementById('conversation_context').value;
            const customPromptContent = document.getElementById('custom-prompt-content').value.trim();
            
            // Get current prompt content if editing and no custom prompt provided
            let promptContent = null;
            if (customPromptContent) {
                promptContent = customPromptContent;
            } else if (currentEditingPrompt && currentEditingPrompt.content) {
                promptContent = currentEditingPrompt.content;
            }
            
            const resultsDiv = document.getElementById('sample-results');
            const outputDiv = document.getElementById('sample-output');
            
            resultsDiv.style.display = 'none';
            outputDiv.textContent = 'Generating sample response...';
            resultsDiv.style.display = 'block';
            
            try {
                const response = await fetch('/api/test-merchants/generate-sample', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt_type: promptType,
                        prompt_content: promptContent,
                        conversation_context: conversationContext
                    })
                });
                
                const data = await response.json();
                if (data.status === 'success' && data.responses && data.responses.length > 0) {
                    const response = data.responses[0];
                    const output = `Subject: ${response.subject}\n\n${response.body}`;
                    outputDiv.textContent = output;
                } else {
                    outputDiv.textContent = 'Error: ' + (data.message || 'Failed to generate sample');
                }
            } catch (error) {
                outputDiv.textContent = 'Error: ' + error.message;
            }
        }
        
        // Show/hide conversation context based on prompt type
        document.getElementById('sample-prompt-type')?.addEventListener('change', (e) => {
            const contextSection = document.getElementById('conversation-context-section');
            if (e.target.value === 'reply-email') {
                contextSection.style.display = 'block';
            } else {
                contextSection.style.display = 'none';
            }
        });
        
        // Test Prompt Function
        async function testPrompt(promptId) {
            const prompts = promptsData[currentPromptType] || [];
            const prompt = prompts.find(p => p.id === promptId);
            if (!prompt) {
                alert('Prompt not found');
                return;
            }
            
            // Skip test for voice guidelines
            if (currentPromptType === 'voice-guidelines') {
                alert('Cannot test voice guidelines. Please use a new-email, reply-email, or non-campaign-email prompt.');
                return;
            }
            
            // Show test panel
            const testPanel = document.getElementById('test-results-panel');
            const testContent = document.getElementById('test-results-content');
            const replyInputSection = document.getElementById('test-reply-input-section');
            const replyInput = document.getElementById('test-reply-input');
            
            testPanel.style.display = 'block';
            
            // Determine prompt type
            const promptType = currentPromptType === 'new-email' ? 'new-email' : (currentPromptType === 'non-campaign-email' ? 'non-campaign-email' : 'reply-email');
            
            // For reply-email and non-campaign-email, show input box and wait for user input
            if (promptType === 'reply-email' || promptType === 'non-campaign-email') {
                replyInputSection.style.display = 'block';
                testContent.innerHTML = 'Enter a message above and click "Generate Reply" to test the prompt.';
                replyInput.value = '';
                replyInput.focus();
                // Store prompt info for later use
                testContent.dataset.promptId = promptId;
                testContent.dataset.promptContent = prompt.content || '';
                testContent.dataset.promptType = promptType;
            } else {
                // For new-email, generate immediately
                replyInputSection.style.display = 'none';
                testContent.innerHTML = 'Generating test response...';
                
                try {
                    const promptContent = prompt.content || '';
                    
                    const response = await fetch('/api/test-merchants/generate-sample', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            prompt_type: promptType,
                            prompt_content: promptContent,
                            conversation_context: ''
                        })
                    });
                    
                    const data = await response.json();
                    if (data.status === 'success' && data.responses && data.responses.length > 0) {
                        const result = data.responses[0];
                        // Display with HTML rendering for proper formatting
                        const output = `<div style="margin-bottom: 16px;"><strong>Subject:</strong> ${result.subject}</div><div style="border-top: 1px solid #e5e7eb; padding-top: 16px;">${result.body}</div>`;
                        testContent.innerHTML = output;
                    } else {
                        testContent.innerHTML = 'Error: ' + (data.message || 'Failed to generate sample. Make sure you have saved a test merchant first.');
                    }
                } catch (error) {
                    testContent.innerHTML = 'Error: ' + error.message;
                }
            }
        }
        
        // Generate Reply Function (for reply-email prompts)
        async function generateTestReply() {
            const replyInput = document.getElementById('test-reply-input');
            const testContent = document.getElementById('test-results-content');
            const messageToReplyTo = replyInput.value.trim();
            
            if (!messageToReplyTo) {
                alert('Please enter a message to reply to');
                return;
            }
            
            // Get stored prompt info
            const promptId = testContent.dataset.promptId;
            const promptContent = testContent.dataset.promptContent || '';
            const promptType = testContent.dataset.promptType || 'reply-email';
            
            if (!promptId) {
                alert('Prompt information not found. Please click "Test" again.');
                return;
            }
            
            testContent.innerHTML = 'Generating reply...';
            
            try {
                const response = await fetch('/api/test-merchants/generate-sample', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt_type: promptType,
                        prompt_content: promptContent,
                        conversation_context: messageToReplyTo
                    })
                });
                
                const data = await response.json();
                if (data.status === 'success' && data.responses && data.responses.length > 0) {
                    const result = data.responses[0];
                    // Display with HTML rendering for proper formatting
                    const output = `<div style="margin-bottom: 16px;"><strong>Subject:</strong> ${result.subject}</div><div style="border-top: 1px solid #e5e7eb; padding-top: 16px;">${result.body}</div>`;
                    testContent.innerHTML = output;
                } else {
                    testContent.innerHTML = 'Error: ' + (data.message || 'Failed to generate reply. Make sure you have saved a test merchant first.');
                }
            } catch (error) {
                testContent.innerHTML = 'Error: ' + error.message;
            }
        }
        
        function closeTestPanel() {
            document.getElementById('test-results-panel').style.display = 'none';
        }
        
        // Delete Prompt Function
        async function deletePrompt(promptId) {
            const prompts = promptsData[currentPromptType] || [];
            const prompt = prompts.find(p => p.id === promptId);
            if (!prompt) {
                alert('Prompt not found');
                return;
            }
            
            // Check if it's a default prompt (no version_letter)
            if (!prompt.version_letter) {
                alert('Cannot delete default prompts. You can only delete version prompts (A, B, C, etc.).');
                return;
            }
            
            // Confirm deletion
            const confirmMessage = `Are you sure you want to delete "${prompt.name}" (Version ${prompt.version_letter})?\n\nThis action cannot be undone.`;
            if (!confirm(confirmMessage)) {
                return;
            }
            
            try {
                // Get the actual version ID from the database
                // The prompt.id is 1000 + version.id, so we need to extract the real version ID
                const versionId = prompt.id - 1000;
                
                const response = await fetch('/api/prompts/delete-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ version_id: versionId })
                });
                
                const data = await response.json();
                if (data.status === 'success') {
                    alert('✅ Prompt version deleted successfully!');
                    await Promise.all([loadAllPrompts(), loadStats()]);
                    renderTable();
                } else {
                    alert('❌ Error: ' + data.message);
                }
            } catch (error) {
                alert('❌ Error deleting prompt: ' + error.message);
            }
        }
    </script>
</body>
</html>
""", 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/prompts/get', methods=['GET'])
def get_prompts():
    """Get all current prompts (from database first, then environment variables, then defaults)."""
    try:
        # Default prompt templates (extracted from code)
        new_email_prompt_default = """Generate a **professional, Affirm-branded business email** to re-engage {merchant_name}, a merchant in the {merchant_industry_str} industry, who has completed technical integration with Affirm but has **not yet launched**. The goal is to encourage them to go live — without offering a meeting or call.

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

Keep the email under 130 words. Make it feel natural and human, not like marketing automation."""

        reply_email_prompt_default = """**TASK:** Generate a professional Affirm-branded email response to {recipient_name} from {sender_name}.

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

For all support, refer to customercare@affirm.com Only."""

        # Default prompt for non-campaign emails
        non_campaign_email_prompt_default = """{AFFIRM_VOICE_GUIDELINES}

**TASK:** Generate a professional, Affirm-branded email response to {sender_name} who reached out but is not part of an active campaign. Politely direct them to merchantcare@affirm.com for merchant support and inquiries.

**CONTEXT:**
- Sender: {sender_name}
- Recipient: Jake Morgan (Business Development)
- Email Body: {email_body}

**CRITICAL RULES:**
1. **Be polite and professional** - acknowledge their outreach
2. **Direct them to merchantcare@affirm.com** - this is the main purpose
3. **Be helpful** - explain that Merchant Care can assist with their questions
4. **Keep it brief** - under 100 words
5. **Maintain Affirm brand voice** - smart, approachable, efficient

**OUTPUT FORMAT:**
- **Email Body:** [Your response in HTML format]

For all merchant support, refer to merchantcare@affirm.com only."""

        # Try to get from database first (from prompt_versions table with version_letter = 'DEFAULT')
        new_email_prompt = None
        reply_email_prompt = None
        non_campaign_email_prompt = None
        voice_guidelines = None
        
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    
                    # Get saved default prompts from prompt_versions table
                    cursor.execute('''
                        SELECT prompt_type, prompt_content
                        FROM prompt_versions
                        WHERE version_letter = 'DEFAULT'
                    ''')
                    
                    for row in cursor.fetchall():
                        prompt_type, content = row
                        if prompt_type == 'new-email':
                            new_email_prompt = content
                        elif prompt_type == 'reply-email':
                            reply_email_prompt = content
                        elif prompt_type == 'non-campaign-email':
                            non_campaign_email_prompt = content
                    
                    conn.close()
                    logger.info(f"📝 Loaded prompts from database: new_email={bool(new_email_prompt)}, reply_email={bool(reply_email_prompt)}, non_campaign_email={bool(non_campaign_email_prompt)}")
            except Exception as e:
                logger.warning(f"Could not load prompts from database: {e}")
        
        # Fall back to environment variables if not in database
        if not new_email_prompt:
            new_email_prompt = os.getenv('NEW_EMAIL_PROMPT_TEMPLATE', new_email_prompt_default)
        if not reply_email_prompt:
            reply_email_prompt = os.getenv('REPLY_EMAIL_PROMPT_TEMPLATE', reply_email_prompt_default)
        if not non_campaign_email_prompt:
            non_campaign_email_prompt = os.getenv('NON_CAMPAIGN_EMAIL_PROMPT_TEMPLATE', non_campaign_email_prompt_default)
        if not voice_guidelines:
            voice_guidelines = os.getenv('AFFIRM_VOICE_GUIDELINES', AFFIRM_VOICE_GUIDELINES)
        
        # Update environment variables to keep them in sync
        os.environ['NEW_EMAIL_PROMPT_TEMPLATE'] = new_email_prompt
        os.environ['REPLY_EMAIL_PROMPT_TEMPLATE'] = reply_email_prompt
        os.environ['NON_CAMPAIGN_EMAIL_PROMPT_TEMPLATE'] = non_campaign_email_prompt
        os.environ['AFFIRM_VOICE_GUIDELINES'] = voice_guidelines
        
        return jsonify({
            'status': 'success',
            'prompts': {
                'voice_guidelines': voice_guidelines,
                'new_email_prompt': new_email_prompt,
                'reply_email_prompt': reply_email_prompt,
                'non_campaign_email_prompt': non_campaign_email_prompt
            },
            'endpoints': {
                'voice_guidelines': 'Used in all email prompts',
                'new_email_prompt': '/api/workato/send-new-email',
                'reply_email_prompt': '/api/workato/reply-to-emails'
            }
        })
    except Exception as e:
        logger.error(f"Error getting prompts: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/prompts/update', methods=['POST'])
def update_prompt():
    """Update a default prompt (stores in database and environment variable)."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        data = request.get_json()
        prompt_key = data.get('key')
        prompt_value = data.get('value')
        
        if not prompt_key or not prompt_value:
            return jsonify({
                'status': 'error',
                'message': 'Missing key or value'
            }), 400
        
        logger.info(f"📝 Prompt update requested: {prompt_key}")
        logger.info(f"📝 New prompt value (first 200 chars): {prompt_value[:200]}...")
        logger.info(f"📝 Prompt length: {len(prompt_value)} characters")
        
        # Map prompt_key to prompt_type and endpoint
        prompt_type_map = {
            'NEW_EMAIL_PROMPT_TEMPLATE': ('new-email', '/api/workato/send-new-email'),
            'REPLY_EMAIL_PROMPT_TEMPLATE': ('reply-email', '/api/workato/reply-to-emails'),
            'NON_CAMPAIGN_EMAIL_PROMPT_TEMPLATE': ('non-campaign-email', '/api/workato/check-non-campaign-emails')
        }
        
        if prompt_key not in prompt_type_map:
            return jsonify({
                'status': 'error',
                'message': f'Invalid prompt key: {prompt_key}. Only NEW_EMAIL_PROMPT_TEMPLATE and REPLY_EMAIL_PROMPT_TEMPLATE are supported.'
            }), 400
        
        prompt_type, endpoint_path = prompt_type_map[prompt_key]
        
        # Save to database using prompt_versions table with version_letter = 'DEFAULT'
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Check if default prompt already exists
        cursor.execute('''
            SELECT id FROM prompt_versions 
            WHERE prompt_type = %s AND version_letter = 'DEFAULT'
        ''', (prompt_type,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing default prompt
            cursor.execute('''
                UPDATE prompt_versions
                SET prompt_content = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE prompt_type = %s AND version_letter = 'DEFAULT'
            ''', (prompt_value, prompt_type))
            logger.info(f"✅ Updated existing default prompt {prompt_key} in database")
        else:
            # Insert new default prompt
            cursor.execute('''
                INSERT INTO prompt_versions 
                (version_name, prompt_type, prompt_content, version_letter, endpoint_path, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', ('Default Version', prompt_type, prompt_value, 'DEFAULT', endpoint_path, 'active'))
            logger.info(f"✅ Created new default prompt {prompt_key} in database")
        
        conn.commit()
        conn.close()
        
        # Also update the environment variable for immediate use
        os.environ[prompt_key] = prompt_value
        
        logger.info(f"✅ Prompt {prompt_key} saved to database and updated in memory. Changes take effect immediately.")
        
        return jsonify({
            'status': 'success',
            'message': f'Prompt {prompt_key} saved successfully. Changes take effect immediately for new emails.',
            'key': prompt_key
        })
    except Exception as e:
        logger.error(f"Error updating prompt: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/prompts/reset', methods=['POST'])
def reset_prompt():
    """Reset a prompt to its default value."""
    try:
        data = request.get_json()
        prompt_key = data.get('key')
        
        if not prompt_key:
            return jsonify({
                'status': 'error',
                'message': 'Missing key'
            }), 400
        
        # Default values
        defaults = {
            'AFFIRM_VOICE_GUIDELINES': AFFIRM_VOICE_GUIDELINES,
            'NEW_EMAIL_PROMPT_TEMPLATE': '',  # Will be extracted from code
            'REPLY_EMAIL_PROMPT_TEMPLATE': ''  # Will be extracted from code
        }
        
        default_value = defaults.get(prompt_key, '')
        
        # Reset to default
        if prompt_key in defaults:
            os.environ[prompt_key] = default_value
        
        return jsonify({
            'status': 'success',
            'message': f'Prompt {prompt_key} reset to default',
            'default_value': default_value
        })
    except Exception as e:
        logger.error(f"Error resetting prompt: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/prompts/get-versions', methods=['GET'])
def get_prompt_versions():
    """Get all prompt versions from database."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        prompt_type = request.args.get('prompt_type', '')
        
        cursor = conn.cursor()
        
        if prompt_type:
            cursor.execute('''
                SELECT id, version_name, prompt_type, prompt_content, version_letter, 
                       endpoint_path, status, created_at, updated_at
                FROM prompt_versions
                WHERE prompt_type = %s AND version_letter != 'DEFAULT'
                ORDER BY version_letter
            ''', (prompt_type,))
        else:
            cursor.execute('''
                SELECT id, version_name, prompt_type, prompt_content, version_letter, 
                       endpoint_path, status, created_at, updated_at
                FROM prompt_versions
                WHERE version_letter != 'DEFAULT'
                ORDER BY prompt_type, version_letter
            ''')
        
        versions = []
        for row in cursor.fetchall():
            versions.append({
                'id': row[0],
                'version_name': row[1],
                'prompt_type': row[2],
                'prompt_content': row[3],
                'version_letter': row[4],
                'endpoint_path': row[5],
                'status': row[6],
                'created_at': row[7].isoformat() if row[7] else None,
                'updated_at': row[8].isoformat() if row[8] else None
            })
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'versions': versions
        })
        
    except Exception as e:
        logger.error(f"Error getting prompt versions: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/prompts/get-stats', methods=['GET'])
def get_prompt_version_stats():
    """Get open rate statistics for each prompt version endpoint."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Get stats for each version endpoint
        # Calculate: total sent, total opened, open rate
        # Only count emails that have a version_endpoint set (don't include NULL as default)
        cursor.execute('''
            SELECT 
                et.version_endpoint as endpoint,
                COUNT(DISTINCT et.id) as total_sent,
                COUNT(DISTINCT CASE WHEN et.open_count > 0 THEN et.id END) as total_opened,
                ROUND(
                    CASE 
                        WHEN COUNT(DISTINCT et.id) > 0 
                        THEN (COUNT(DISTINCT CASE WHEN et.open_count > 0 THEN et.id END)::NUMERIC / COUNT(DISTINCT et.id)::NUMERIC) * 100
                        ELSE 0 
                    END::NUMERIC, 
                    2
                ) as open_rate
            FROM email_tracking et
            WHERE et.version_endpoint IS NOT NULL
            GROUP BY et.version_endpoint
            ORDER BY endpoint
        ''')
        
        stats = {}
        for row in cursor.fetchall():
            endpoint, total_sent, total_opened, open_rate = row
            # Normalize endpoint to ensure exact match
            endpoint = endpoint.strip() if endpoint else '/api/workato/send-new-email'
            stats[endpoint] = {
                'total_sent': int(total_sent) if total_sent else 0,
                'total_opened': int(total_opened) if total_opened else 0,
                'open_rate': float(open_rate) if open_rate else 0.0
            }
        
        # Also check what endpoints actually exist in the database for debugging
        cursor.execute('''
            SELECT DISTINCT version_endpoint, COUNT(*) 
            FROM email_tracking 
            GROUP BY version_endpoint
            ORDER BY version_endpoint
        ''')
        endpoint_counts = {row[0]: row[1] for row in cursor.fetchall()}
        logger.info(f"📊 Endpoints in database: {endpoint_counts}")
        
        conn.close()
        
        logger.info(f"📊 Stats calculated: {stats}")
        
        return jsonify({
            'status': 'success',
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting prompt version stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/prompts/create-version', methods=['POST'])
def create_prompt_version():
    """Create a new prompt version and automatically create a versioned endpoint."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        data = request.get_json()
        version_name = data.get('version_name', '').strip()
        prompt_type = data.get('prompt_type', '').strip()  # 'new-email' or 'reply-email'
        prompt_content = data.get('prompt_content', '').strip()
        
        if not version_name or not prompt_type or not prompt_content:
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: version_name, prompt_type, prompt_content'
            }), 400
        
        if prompt_type not in ['new-email', 'reply-email', 'non-campaign-email']:
            return jsonify({
                'status': 'error',
                'message': 'prompt_type must be "new-email", "reply-email", or "non-campaign-email"'
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Find the next available version letter (A, B, C, etc.)
        cursor.execute('''
            SELECT version_letter 
            FROM prompt_versions 
            WHERE prompt_type = %s 
            ORDER BY version_letter
        ''', (prompt_type,))
        existing_versions = [row[0] for row in cursor.fetchall()]
        
        # Generate next version letter
        version_letter = None
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if letter not in existing_versions:
                version_letter = letter
                break
        
        if not version_letter:
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Maximum number of versions reached (26 versions max)'
            }), 400
        
        # Determine endpoint path
        if prompt_type == 'new-email':
            endpoint_path = f'/api/workato/send-new-email-version-{version_letter.lower()}'
        elif prompt_type == 'reply-email':
            endpoint_path = f'/api/workato/reply-to-emails-version-{version_letter.lower()}'
        else:  # non-campaign-email (no versioned endpoints for this type)
            endpoint_path = f'/api/workato/check-non-campaign-emails'
        
        # Insert version into database
        cursor.execute('''
            INSERT INTO prompt_versions 
            (version_name, prompt_type, prompt_content, version_letter, endpoint_path, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (version_name, prompt_type, prompt_content, version_letter, endpoint_path, 'draft'))
        
        version_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        
        # Store endpoint info (routes handled by catch-all)
        create_versioned_endpoint(prompt_type, version_letter, endpoint_path, prompt_content)
        
        logger.info(f"✅ Created prompt version: {version_name} ({version_letter}) with endpoint: {endpoint_path}")
        
        return jsonify({
            'status': 'success',
            'message': f'Prompt version created successfully',
            'version_id': version_id,
            'version_name': version_name,
            'version_letter': version_letter,
            'endpoint_path': endpoint_path,
            'prompt_type': prompt_type
        })
        
    except Exception as e:
        logger.error(f"❌ Error creating prompt version: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error creating prompt version: {str(e)}'
        }), 500

@app.route('/api/prompts/update-version', methods=['POST'])
def update_prompt_version():
    """Update an existing prompt version in the database and update the dynamic endpoint."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        data = request.get_json()
        version_id = data.get('version_id')
        prompt_content = data.get('prompt_content', '').strip()
        
        if not version_id or not prompt_content:
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: version_id, prompt_content'
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Get the existing version to get its details
        logger.info(f"📝 Updating prompt version with ID: {version_id}")
        cursor.execute('''
            SELECT prompt_type, version_letter, endpoint_path, version_name
            FROM prompt_versions
            WHERE id = %s
        ''', (version_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            logger.error(f"❌ Prompt version with ID {version_id} not found in database")
            return jsonify({
                'status': 'error',
                'message': f'Prompt version with ID {version_id} not found'
            }), 404
        
        logger.info(f"✅ Found prompt version: {row[3]} (ID: {version_id})")
        
        prompt_type, version_letter, endpoint_path, version_name = row
        
        # Update the prompt content in the database
        cursor.execute('''
            UPDATE prompt_versions
            SET prompt_content = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (prompt_content, version_id))
        
        conn.commit()
        conn.close()
        
        # Update the dynamic endpoint with the new prompt content
        create_versioned_endpoint(prompt_type, version_letter, endpoint_path, prompt_content)
        
        logger.info(f"✅ Updated prompt version {version_id} ({version_letter}) with new content")
        logger.info(f"📝 Updated prompt content (first 200 chars): {prompt_content[:200]}...")
        
        return jsonify({
            'status': 'success',
            'message': f'Prompt version updated successfully',
            'version_id': version_id,
            'version_letter': version_letter,
            'endpoint_path': endpoint_path
        })
        
    except Exception as e:
        logger.error(f"❌ Error updating prompt version: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error updating prompt version: {str(e)}'
        }), 500

@app.route('/api/prompts/delete-version', methods=['POST'])
def delete_prompt_version():
    """Delete a prompt version from the database."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        data = request.get_json()
        version_id = data.get('version_id')
        
        if not version_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: version_id'
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Get version info before deleting (for logging)
        cursor.execute('''
            SELECT version_name, version_letter, endpoint_path, prompt_type
            FROM prompt_versions
            WHERE id = %s
        ''', (version_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Prompt version not found'
            }), 404
        
        version_name, version_letter, endpoint_path, prompt_type = row
        
        # Delete the version from database
        cursor.execute('''
            DELETE FROM prompt_versions
            WHERE id = %s
        ''', (version_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Deleted prompt version {version_id} ({version_letter}): {version_name}")
        
        return jsonify({
            'status': 'success',
            'message': f'Prompt version "{version_name}" (Version {version_letter}) deleted successfully',
            'version_id': version_id,
            'version_letter': version_letter
        })
        
    except Exception as e:
        logger.error(f"❌ Error deleting prompt version: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error deleting prompt version: {str(e)}'
        }), 500

# Store dynamically created endpoints
_dynamic_endpoints = {}

def create_versioned_endpoint(prompt_type, version_letter, endpoint_path, prompt_content):
    """Store versioned endpoint info (routes are handled by catch-all route)."""
    global _dynamic_endpoints
    
    # Store for reference (no longer creating routes dynamically)
    _dynamic_endpoints[endpoint_path] = {
        'prompt_type': prompt_type,
        'version_letter': version_letter,
        'prompt_content': prompt_content
    }
    
    logger.info(f"✅ Registered versioned endpoint info: {endpoint_path} (will be handled by catch-all route)")

def get_versioned_prompt_from_db(endpoint_path):
    """Get prompt content for a versioned endpoint from the database."""
    try:
        if not DB_AVAILABLE:
            return None
        
        conn = get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT prompt_type, prompt_content, version_letter
            FROM prompt_versions
            WHERE endpoint_path = %s AND status = 'active'
        ''', (endpoint_path,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'prompt_type': row[0],
                'prompt_content': row[1],
                'version_letter': row[2]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting versioned prompt from DB: {e}")
        return None

# Load existing versions and create endpoints on startup
def load_prompt_versions():
    """Load existing prompt versions from database and create their endpoints."""
    try:
        if not DB_AVAILABLE:
            return
        
        conn = get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT prompt_type, version_letter, endpoint_path, prompt_content
            FROM prompt_versions
            WHERE status = 'active'
        ''')
        
        for row in cursor.fetchall():
            prompt_type, version_letter, endpoint_path, prompt_content = row
            create_versioned_endpoint(prompt_type, version_letter, endpoint_path, prompt_content)
            logger.info(f"✅ Loaded existing version endpoint: {endpoint_path}")
        
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ Could not load prompt versions: {e}")

# Load versions on startup (just store info, routes handled by catch-all)
load_prompt_versions()

# Catch-all route for versioned send-new-email endpoints
@app.route('/api/workato/send-new-email-version-<version_letter>', methods=['POST'])
def handle_versioned_send_new_email(version_letter):
    """Handle versioned send-new-email endpoints by looking up prompt from database."""
    endpoint_path = f'/api/workato/send-new-email-version-{version_letter.lower()}'
    
    # Get prompt from database
    version_info = get_versioned_prompt_from_db(endpoint_path)
    if not version_info:
        return jsonify({
            "status": "error",
            "message": f"Version {version_letter.upper()} not found or not active",
            "timestamp": datetime.datetime.now().isoformat()
        }), 404
    
    prompt_content = version_info['prompt_content']
    version_letter_upper = version_info['version_letter']
    
    try:
        # Get the same logic as workato_send_new_email but with custom prompt
        data = request.get_json() if request.is_json else {}
        
        # Extract all the same fields as the original endpoint
        contact_name = data.get('contact_name', '')
        contact_email = data.get('contact_email', '')
        contact_title = data.get('contact_title', '')
        account_name = data.get('account_name', '')
        account_industry = data.get('account_industry', 'Business')
        account_website = data.get('account_website', '')
        account_description = data.get('account_description', '')
        
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
        account_id = data.get('account_id', '')
        
        activities = data.get('activities', [])
        sender_name = "Jake Morgan"
        
        if not contact_email:
            return jsonify({
                "status": "error",
                "message": "Missing required 'contact_email' parameter",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        # Check if email has already been sent
        has_been_sent, reason = check_if_email_already_sent(contact_email, activities)
        if has_been_sent:
            return jsonify({
                "status": "skipped",
                "message": f"Email already sent to this contact - {reason}",
                "timestamp": datetime.datetime.now().isoformat(),
                "contact": contact_name,
                "account": account_name,
                "reason": reason,
                "emails_sent": 0
            }), 200
        
        # Log which version is being used
        logger.info(f"📝 PROMPT VERSION BEING USED:")
        logger.info(f"   Endpoint: {endpoint_path}")
        logger.info(f"   Version Letter: {version_letter_upper}")
        logger.info(f"   Prompt Content Length: {len(prompt_content)} characters")
        
        # Generate email using custom prompt template
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
            account_gmv=account_gmv,
            prompt_template=prompt_content
        )
        
        # Format and send email
        formatted_email = format_pardot_email(
            first_name=contact_name,
            email_content=email_content,
            recipient_email=contact_email,
            sender_name=sender_name
        )
        
        email_result = send_email(
            to_email=contact_email,
            merchant_name=contact_name,
            subject_line=subject_line,
            email_content=formatted_email,
            campaign_name="MSS Signed But Not Activated Campaign",
            version_endpoint=endpoint_path
        )
        
        email_status = email_result['status'] if isinstance(email_result, dict) else email_result
        tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""
        
        clean_email_body = email_content.replace('\n', ' ').replace('\r', ' ').strip()
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
            "emails_sent": 1,
            "version": version_letter_upper
        })
        
    except Exception as e:
        logger.error(f"❌ Error in versioned send-new-email endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error sending email: {str(e)}",
            "timestamp": datetime.datetime.now().isoformat()
        }), 500

@app.route('/api/workato/reply-to-emails-version-<version_letter>', methods=['POST'])
def handle_versioned_reply_to_emails(version_letter):
    """Handle versioned reply-to-emails endpoints by looking up prompt from database."""
    endpoint_path = f'/api/workato/reply-to-emails-version-{version_letter.lower()}'
    
    # Get prompt from database
    version_info = get_versioned_prompt_from_db(endpoint_path)
    if not version_info:
        return jsonify({
            "status": "error",
            "message": f"Version {version_letter.upper()} not found or not active",
            "timestamp": datetime.datetime.now().isoformat()
        }), 404
    
    return jsonify({
        "status": "error",
        "message": "Reply email versions not yet implemented",
        "timestamp": datetime.datetime.now().isoformat()
    }), 501

@app.route('/api/test-merchants/save', methods=['POST', 'GET'])
def save_test_merchant():
    """
    Save or update test merchant data.
    Works with Workato - accepts both POST (JSON body) and GET (query parameters).
    
    Expected fields:
    - merchant_name (required)
    - contact_email
    - contact_title
    - merchant_industry
    - merchant_website
    - account_description
    - account_revenue (number)
    - account_employees (number)
    - account_location
    - account_gmv (number)
    - last_activity
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        # Support both POST (JSON) and GET (query params) for Workato compatibility
        if request.method == 'GET':
            data = request.args.to_dict()
            # Convert string numbers to appropriate types
            if 'account_revenue' in data:
                try:
                    data['account_revenue'] = float(data['account_revenue']) if data['account_revenue'] else 0
                except (ValueError, TypeError):
                    data['account_revenue'] = 0
            if 'account_employees' in data:
                try:
                    data['account_employees'] = int(data['account_employees']) if data['account_employees'] else 0
                except (ValueError, TypeError):
                    data['account_employees'] = 0
            if 'account_gmv' in data:
                try:
                    data['account_gmv'] = float(data['account_gmv']) if data['account_gmv'] else 0
                except (ValueError, TypeError):
                    data['account_gmv'] = 0
        else:
            data = request.get_json() if request.is_json else {}
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        
        # Check if test merchant already exists (we'll only keep one test merchant)
        cursor.execute('SELECT id FROM test_merchants LIMIT 1')
        existing = cursor.fetchone()
        
        # Map fields from send-new-email format if merchant_name is not provided
        # This allows using the same request body as /api/workato/send-new-email
        if 'merchant_name' not in data and 'contact_name' in data:
            merchant_name = data.get('contact_name', 'Test Merchant')
        else:
            merchant_name = data.get('merchant_name', data.get('contact_name', 'Test Merchant'))
        
        contact_email = data.get('contact_email', '')
        contact_title = data.get('contact_title', '')
        
        # Map account fields to merchant fields
        merchant_industry = data.get('merchant_industry', data.get('account_industry', ''))
        merchant_website = data.get('merchant_website', data.get('account_website', ''))
        account_description = data.get('account_description', '')
        
        # Handle numeric fields with proper conversion
        account_revenue = data.get('account_revenue', 0) or 0
        if isinstance(account_revenue, str):
            try:
                account_revenue = float(account_revenue) if account_revenue else 0
            except (ValueError, TypeError):
                account_revenue = 0
        
        account_employees = data.get('account_employees', 0) or 0
        if isinstance(account_employees, str):
            try:
                account_employees = int(account_employees) if account_employees else 0
            except (ValueError, TypeError):
                account_employees = 0
        
        # Map location from account_city and account_state if account_location not provided
        account_location = data.get('account_location', '')
        if not account_location:
            account_city = data.get('account_city', '')
            account_state = data.get('account_state', '')
            if account_city or account_state:
                account_location = f"{account_city}, {account_state}".strip(", ")
        
        account_gmv = data.get('account_gmv', 0) or 0
        if isinstance(account_gmv, str):
            try:
                account_gmv = float(account_gmv) if account_gmv else 0
            except (ValueError, TypeError):
                account_gmv = 0
        
        last_activity = data.get('last_activity', 'Recent')
        
        if existing:
            # Update existing test merchant
            cursor.execute('''
                UPDATE test_merchants SET
                    merchant_name = %s,
                    contact_email = %s,
                    contact_title = %s,
                    merchant_industry = %s,
                    merchant_website = %s,
                    account_description = %s,
                    account_revenue = %s,
                    account_employees = %s,
                    account_location = %s,
                    account_gmv = %s,
                    last_activity = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (merchant_name, contact_email, contact_title, merchant_industry, merchant_website,
                  account_description, account_revenue, account_employees, account_location,
                  account_gmv, last_activity, existing[0]))
            logger.info(f"✅ Updated test merchant: {merchant_name}")
        else:
            # Insert new test merchant
            cursor.execute('''
                INSERT INTO test_merchants 
                (merchant_name, contact_email, contact_title, merchant_industry, merchant_website,
                 account_description, account_revenue, account_employees, account_location,
                 account_gmv, last_activity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (merchant_name, contact_email, contact_title, merchant_industry, merchant_website,
                  account_description, account_revenue, account_employees, account_location,
                  account_gmv, last_activity))
            logger.info(f"✅ Created test merchant: {merchant_name}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Test merchant saved via {'GET' if request.method == 'GET' else 'POST'}: {merchant_name}")
        
        return jsonify({
            'status': 'success',
            'message': 'Test merchant saved successfully',
            'merchant_name': merchant_name,
            'timestamp': datetime.datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving test merchant: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/test-merchants/get', methods=['GET'])
def get_test_merchant():
    """Get the saved test merchant data."""
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, merchant_name, contact_email, contact_title, merchant_industry,
                   merchant_website, account_description, account_revenue, account_employees,
                   account_location, account_gmv, last_activity
            FROM test_merchants
            ORDER BY updated_at DESC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'status': 'success',
                'merchant': {
                    'id': row[0],
                    'merchant_name': row[1],
                    'contact_email': row[2],
                    'contact_title': row[3],
                    'merchant_industry': row[4],
                    'merchant_website': row[5],
                    'account_description': row[6],
                    'account_revenue': float(row[7]) if row[7] else 0,
                    'account_employees': row[8] if row[8] else 0,
                    'account_location': row[9],
                    'account_gmv': float(row[10]) if row[10] else 0,
                    'last_activity': row[11]
                }
            })
        else:
            return jsonify({
                'status': 'success',
                'merchant': None
            })
    except Exception as e:
        logger.error(f"Error getting test merchant: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/test-merchants/generate-sample', methods=['POST'])
def generate_sample_response():
    """Generate sample email responses using test merchant data and specified prompt."""
    try:
        data = request.get_json()
        prompt_type = data.get('prompt_type', 'new-email')  # 'new-email' or 'reply-email'
        prompt_content = data.get('prompt_content', None)  # Optional custom prompt
        conversation_context = data.get('conversation_context', '')  # For reply emails
        
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available'
            }), 503
        
        # Get test merchant data
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed'
            }), 503
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT merchant_name, contact_email, contact_title, merchant_industry,
                   merchant_website, account_description, account_revenue, account_employees,
                   account_location, account_gmv, last_activity
            FROM test_merchants
            ORDER BY updated_at DESC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                'status': 'error',
                'message': 'No test merchant found. Please save test merchant data first.'
            }), 400
        
        merchant_name = row[0]
        contact_email = row[1] or 'test@example.com'
        contact_title = row[2] or ''
        merchant_industry = row[3] or 'Business'
        merchant_website = row[4] or ''
        account_description = row[5] or ''
        account_revenue = float(row[6]) if row[6] else 0
        account_employees = row[7] if row[7] else 0
        account_location = row[8] or ''
        account_gmv = float(row[9]) if row[9] else 0
        last_activity = row[10] or 'Recent'
        
        sender_name = "Jake Morgan"
        responses = []
        
        if prompt_type == 'new-email':
            # Generate new email sample
            subject_line, email_content = generate_message(
                merchant_name=merchant_name,
                last_activity=last_activity,
                merchant_industry=merchant_industry,
                merchant_website=merchant_website,
                sender_name=sender_name,
                account_description=account_description,
                account_revenue=account_revenue,
                account_employees=account_employees,
                account_location=account_location,
                contact_title=contact_title,
                account_gmv=account_gmv,
                prompt_template=prompt_content
            )
            
            responses.append({
                'type': 'new-email',
                'subject': subject_line,
                'body': email_content,
                'merchant_name': merchant_name
            })
            
        elif prompt_type == 'reply-email' or prompt_type == 'non-campaign-email':
            # Generate reply email sample (works for both reply-email and non-campaign-email)
            # Use a sample email body if no conversation context provided
            sample_email_body = conversation_context or f"Hi Jake,\n\nI'm interested in learning more about Affirm. Can you tell me more about how it works?\n\nThanks,\n{merchant_name}"
            
            ai_response = generate_ai_response(
                email_body=sample_email_body,
                sender_name=sender_name,
                recipient_name=merchant_name,
                conversation_history=conversation_context if conversation_context else None,
                prompt_template=prompt_content  # Use the custom prompt from frontend if provided
            )
            
            # Return the full HTML email (not just body content) for proper rendering
            email_body = ai_response
            
            responses.append({
                'type': prompt_type,
                'subject': f"Re: Your Message",
                'body': email_body,
                'merchant_name': merchant_name
            })
        
        return jsonify({
            'status': 'success',
            'responses': responses,
            'test_merchant': {
                'merchant_name': merchant_name,
                'merchant_industry': merchant_industry,
                'contact_title': contact_title
            }
        })
        
    except Exception as e:
        logger.error(f"Error generating sample response: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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
        version_endpoint = data.get('version_endpoint')  # Get version endpoint if provided
        # Default to the main endpoint if not provided
        if not version_endpoint:
            version_endpoint = '/api/workato/send-new-email'
        
        logger.info(f"📝 Tracking email send: {tracking_id} -> {recipient_email} | version_endpoint: {version_endpoint}")
        
        cursor.execute('''
            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name, status, version_endpoint)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (tracking_id, recipient_email, sender_email, subject, campaign_name, 'AI Outbound Email', version_endpoint))
        
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
                            INSERT INTO email_tracking (tracking_id, recipient_email, sender_email, subject, campaign_name, status)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (tracking_id) DO NOTHING
                        ''', (tracking_id, 'unknown@example.com', 'unknown@example.com', 'Unknown', 'Unknown', 'AI Outbound Email'))
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
                    # Update open count and status
                        cursor.execute('''
                            UPDATE email_tracking 
                            SET open_count = open_count + 1, 
                                last_opened_at = CURRENT_TIMESTAMP,
                                status = 'Email Open'
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
        "campaign_name": "MSS Signed But Not Activated Campaign",  # Filter by campaign
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
                created_at,
                sfdc_task_id,
                status
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

@app.route('/api/workato/get-all-email-opens', methods=['POST', 'GET'])
def workato_get_all_email_opens():
    """
    Workato endpoint to get all email open records from email_opens table.
    Supports both GET and POST requests.
    
    Optional query parameters (GET) or body (POST):
    {
        "limit": 100,           # Max number of records (default: 1000)
        "offset": 0,           # Pagination offset (default: 0)
        "order_by": "opened_at",  # Field to order by (default: "opened_at")
        "order_direction": "DESC",  # ASC or DESC (default: "DESC")
        "tracking_id": "abc-123-def-456"  # Filter by tracking_id
    }
    
    Returns:
    {
        "status": "success",
        "total_count": 150,
        "returned_count": 100,
        "offset": 0,
        "limit": 100,
        "opens": [
            {
                "id": 1,
                "tracking_id": "abc-123-def-456",
                "opened_at": "2025-11-27T18:00:00",
                "user_agent": "Mozilla/5.0...",
                "ip_address": "192.168.1.1",
                "referer": "https://..."
            },
            ...
        ]
    }
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        cursor = conn.cursor()
        
        # Get parameters from request
        if request.method == 'GET':
            limit = int(request.args.get('limit', 1000))
            offset = int(request.args.get('offset', 0))
            order_by = request.args.get('order_by', 'opened_at')
            order_direction = request.args.get('order_direction', 'DESC').upper()
            tracking_id_filter = request.args.get('tracking_id', '').strip()
        else:  # POST
            data = request.get_json() if request.is_json else {}
            limit = int(data.get('limit', 1000))
            offset = int(data.get('offset', 0))
            order_by = data.get('order_by', 'opened_at')
            order_direction = data.get('order_direction', 'DESC').upper()
            tracking_id_filter = data.get('tracking_id', '').strip()
        
        # Validate order_by field (prevent SQL injection)
        allowed_order_fields = ['id', 'tracking_id', 'opened_at', 'user_agent', 'ip_address', 'referer']
        if order_by not in allowed_order_fields:
            order_by = 'opened_at'
        
        # Validate order_direction
        if order_direction not in ['ASC', 'DESC']:
            order_direction = 'DESC'
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if tracking_id_filter:
            where_conditions.append("tracking_id = %s")
            params.append(tracking_id_filter)
        
        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM email_opens{where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Get records
        query = f"""
            SELECT 
                id,
                tracking_id,
                opened_at,
                user_agent,
                ip_address,
                referer
            FROM email_opens
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
            'opens': records,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting email opens: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error getting email opens: {str(e)}',
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
        
        logger.info(f"🤖 Using OpenAI model: {OPENAI_MODEL}")
        logger.info(f"🤖 Testing OpenAI connection...")
        # Simple test request
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
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
        
        # Format response with actual email and thread details
        email_details = []
        if 'responses' in result and result['responses']:
            import re
            for response in result['responses']:
                # Clean AI response for display
                ai_response_text = response.get('ai_response', '')
                if ai_response_text:
                    # Remove HTML tags
                    clean_response = re.sub(r'<[^>]+>', '', ai_response_text)
                    # Remove line breaks and extra whitespace
                    clean_response = clean_response.replace('\n', ' ').replace('\r', ' ').strip()
                    clean_response = re.sub(r'\s+', ' ', clean_response)
                else:
                    clean_response = ''
                
                # Build email detail object
                # Extract tracking_id - this is the tracking ID of the reply email that was sent
                tracking_id = response.get('tracking_id') or None
                tracking_url = response.get('tracking_url') or None
                
                email_detail = {
                    "thread_id": response.get('thread_id', 'No ID'),
                    "sender": response.get('sender', ''),
                    "contact_name": response.get('contact_name', ''),
                    "subject": response.get('subject', ''),
                    "original_message": response.get('original_message', ''),
                    "ai_response": clean_response,
                    "email_status": response.get('email_status', ''),
                    "reply_tracking_id": tracking_id,  # Tracking ID of the reply email that was sent
                    "reply_tracking_url": tracking_url,  # Tracking URL for the reply email
                    "tracking_id": tracking_id,  # Also include as tracking_id for backward compatibility
                    "tracking_url": tracking_url,  # Also include as tracking_url for backward compatibility
                    "account_id": response.get('account_id'),
                    "salesforce_id": response.get('salesforce_id')
                }
                email_details.append(email_detail)
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {result.get("emails_processed", 0)} conversation thread(s)',
            'timestamp': datetime.datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_processed': result.get('emails_processed', 0),
            'replies_sent': result.get('replies_sent', result.get('emails_processed', 0)),
            'emails': email_details
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
                
                # Handle the case where activities is a string containing Ruby array syntax
                # Example: "[{"id"=>"...", "subject"=>"..."}, ...]"
                normalized = activities.strip()
                
                # Remove outer quotes if present
                if normalized.startswith('"') and normalized.endswith('"'):
                    normalized = normalized[1:-1]
                
                # Replace Ruby hash syntax => with : (but be careful with spacing)
                # Pattern: "key"=>"value" becomes "key":"value"
                normalized = re.sub(r'"([^"]+)"\s*=>\s*', r'"\1":', normalized)
                normalized = re.sub(r"'([^']+)'\s*=>\s*", r'"\1":', normalized)
                
                # Replace single quotes with double quotes for keys
                normalized = re.sub(r"'([^']+)':", r'"\1":', normalized)
                
                # Try to parse as JSON first
                try:
                    parsed = json.loads(normalized)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        if 'Task' in parsed:
                            return parsed['Task']
                        # Look for any array values
                        for key, value in parsed.items():
                            if isinstance(value, list):
                                return value
                        return []
                except (json.JSONDecodeError, ValueError):
                    # Try ast.literal_eval as fallback
                    try:
                        parsed = ast.literal_eval(normalized)
                        if isinstance(parsed, list):
                            return parsed
                        elif isinstance(parsed, dict):
                            if 'Task' in parsed:
                                return parsed['Task']
                            for key, value in parsed.items():
                                if isinstance(value, list):
                                    return value
                            return []
                    except (ValueError, SyntaxError):
                        # Last resort: try to extract array using regex
                        # Look for array-like structure
                        array_match = re.search(r'\[(.*)\]', normalized, re.DOTALL)
                        if array_match:
                            logger.warning("⚠️ Could not fully parse activities, but found array structure")
                            # Return a simple indicator that activities exist
                            return [{'Type': 'Task', 'Subject': 'Sent AI-Generated Outreach', 'Status': 'Completed'}]
                        raise
            except (json.JSONDecodeError, ValueError, SyntaxError, Exception) as e:
                logger.warning(f"⚠️ Could not parse activities string: {e}")
                logger.debug(f"⚠️ Activities string preview: {activities[:500]}")
                # Last resort: simple string check for email indicators
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
            # Try to parse manually if standard JSON parsing fails
            logger.warning(f"⚠️ Standard JSON parsing failed: {json_error}, attempting manual parse")
            try:
                import json
                import re
                raw_data = request.get_data(as_text=True)
                
                # Try to fix common issues with activities field containing Ruby hash syntax
                # Pattern: "activities": "[{"id"=>"...", ...}]"
                # The activities field is a string containing Ruby hash syntax that needs to be converted to JSON
                if '"activities":' in raw_data:
                    # Find the start of the activities field value
                    activities_start = raw_data.find('"activities":')
                    if activities_start != -1:
                        # Find the colon and the opening quote
                        value_start = raw_data.find('"', activities_start + len('"activities":'))
                        if value_start != -1:
                            # Find the matching closing quote (handle escaped quotes properly)
                            # We need to look for a quote that's not escaped
                            value_end = value_start + 1
                            escaped = False
                            while value_end < len(raw_data):
                                char = raw_data[value_end]
                                if char == '\\':
                                    escaped = not escaped
                                elif char == '"' and not escaped:
                                    break
                                else:
                                    escaped = False
                                value_end += 1
                            
                            if value_end < len(raw_data):
                                # Extract the activities string value
                                activities_str = raw_data[value_start + 1:value_end]
                                # Unescape the string (handle escaped quotes and newlines)
                                # First, handle escaped backslashes, then escaped quotes
                                activities_str = activities_str.replace('\\\\', '\\BACKSLASH_PLACEHOLDER\\')
                                activities_str = activities_str.replace('\\"', '"')
                                activities_str = activities_str.replace('\\n', '\n')
                                activities_str = activities_str.replace('\\BACKSLASH_PLACEHOLDER\\', '\\')
                                # Handle escaped single quotes: \' -> '
                                activities_str = activities_str.replace("\\'", "'")
                                
                                # Convert Ruby hash syntax to JSON
                                # Replace "key"=>"value" with "key":"value"
                                activities_fixed = activities_str
                                
                                # Handle double-quoted keys with double-quoted values: "key"=>"value"
                                # Use a function to properly escape quotes in values
                                def convert_ruby_to_json(match):
                                    key = match.group(1)
                                    value = match.group(2)
                                    # Escape backslashes first, then double quotes for JSON
                                    value = value.replace('\\', '\\\\').replace('"', '\\"')
                                    return f'"{key}": "{value}"'
                                
                                # Match "key"=>"value" where value can contain escaped quotes
                                # The pattern (?:[^"\\]|\\.)* matches any character except unescaped double quotes
                                # We need to be careful - the value part should match until we find an unescaped closing quote
                                # Process in multiple passes to handle nested structures
                                
                                # First pass: convert simple cases "key"=>"value"
                                activities_fixed = re.sub(
                                    r'"([^"]+)"\s*=>\s*"((?:[^"\\]|\\.)*)"',
                                    convert_ruby_to_json,
                                    activities_fixed
                                )
                                
                                # If the regex didn't match everything, try a more aggressive approach
                                # Find all remaining "key"=> patterns and convert them
                                remaining = re.findall(r'"([^"]+)"\s*=>\s*"', activities_fixed)
                                if remaining and '=>' in activities_fixed:
                                    # There are still Ruby hash patterns, try a different approach
                                    # Replace => with : for all remaining cases
                                    activities_fixed = re.sub(r'"([^"]+)"\s*=>\s*"', r'"\1": "', activities_fixed)
                                
                                # Handle double-quoted keys with empty string: "key"=>""
                                activities_fixed = re.sub(r'"([^"]+)"\s*=>\s*""', r'"\1": ""', activities_fixed)
                                
                                # Handle any remaining => with double-quoted keys (for non-string values)
                                activities_fixed = re.sub(r'"([^"]+)"\s*=>\s*', r'"\1": ', activities_fixed)
                                
                                # Handle single-quoted keys (less common but possible)
                                activities_fixed = re.sub(r"'([^']+)'\s*=>\s*'((?:[^'\\]|\\.)*)'", r'"\1": "\2"', activities_fixed)
                                activities_fixed = re.sub(r"'([^']+)'\s*=>\s*", r'"\1": ', activities_fixed)
                                
                                # Replace single quotes with double quotes for remaining keys/values
                                activities_fixed = re.sub(r"'([^']+)':", r'"\1":', activities_fixed)
                                activities_fixed = re.sub(r":\s*'([^']+)'", r': "\1"', activities_fixed)
                                
                                # Try to parse the fixed activities to validate it's valid JSON
                                try:
                                    json.loads(activities_fixed)  # Validate it's valid JSON
                                    # Replace the malformed activities in raw_data
                                    # Remove the quotes around the activities value and use the fixed version
                                    old_activities = raw_data[activities_start:value_end + 1]
                                    new_activities = f'"activities": {activities_fixed}'
                                    raw_data = raw_data[:activities_start] + new_activities + raw_data[value_end + 1:]
                                    logger.info(f"🔍 Fixed activities field (length: {len(old_activities)} -> {len(new_activities)})")
                                except json.JSONDecodeError as e:
                                    logger.warning(f"⚠️ Could not fix activities field to valid JSON: {e}")
                                    logger.debug(f"⚠️ Activities string preview: {activities_str[:300]}")
                                    logger.debug(f"⚠️ Activities fixed preview: {activities_fixed[:300]}")
                                    
                                    # Try one more time with a simpler approach - just replace => with : globally
                                    try:
                                        activities_simple = activities_str.replace('=>', ':')
                                        # Validate the simple replacement
                                        json.loads(activities_simple)
                                        old_activities = raw_data[activities_start:value_end + 1]
                                        new_activities = f'"activities": {activities_simple}'
                                        raw_data = raw_data[:activities_start] + new_activities + raw_data[value_end + 1:]
                                        logger.info(f"🔍 Fixed activities field using simple replacement (=> to :)")
                                    except Exception as simple_error:
                                        logger.debug(f"⚠️ Simple replacement also failed: {simple_error}")
                                        # Remove the activities field entirely to allow the rest to parse
                                        # The issue is that the activities field value contains nested quotes and escaped characters
                                        # We need to find the closing quote that's not escaped by scanning character by character
                                        
                                        # Find where the activities field value starts (after the colon and opening quote)
                                        colon_pos = raw_data.find(':', activities_start)
                                        if colon_pos == -1:
                                            colon_pos = activities_start + len('"activities"')
                                        
                                        # Find the opening quote of the value
                                        value_start_quote = raw_data.find('"', colon_pos)
                                        if value_start_quote == -1:
                                            logger.warning("⚠️ Could not find opening quote for activities field value")
                                            # Fallback: just remove from activities_start to next newline
                                            next_newline = raw_data.find('\n', activities_start)
                                            if next_newline != -1:
                                                raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_newline:]
                                        else:
                                            # Instead of trying to find the closing quote (which is error-prone with nested quotes),
                                            # look for the newline that comes after the activities field value
                                            # The activities field is the last field, so it should be: "activities": "[...]"\n}
                                            # We'll find the newline after the activities field value
                                            
                                            # Find the newline that comes after the activities field value
                                            # Start searching from after the opening quote
                                            search_start = value_start_quote + 1
                                            next_newline = raw_data.find('\n', search_start)
                                            
                                            if next_newline != -1:
                                                # Check if there's a closing brace right after the newline (activities is the last field)
                                                after_newline = raw_data[next_newline+1:next_newline+10].strip()
                                                if after_newline.startswith('}'):
                                                    # Perfect - activities is the last field, replace up to the newline
                                                    raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_newline:]
                                                    logger.info(f"🔍 Removed malformed activities field by finding newline before closing brace, set to empty array")
                                                else:
                                                    # There might be more content, but let's still replace up to the newline
                                                    # This should work since activities is typically the last field
                                                    raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_newline:]
                                                    logger.info(f"🔍 Removed malformed activities field by finding newline, set to empty array")
                                            else:
                                                # No newline found, try to find closing brace
                                                next_brace = raw_data.find('}', search_start)
                                                if next_brace != -1:
                                                    raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_brace:]
                                                    logger.info(f"🔍 Removed malformed activities field by finding closing brace, set to empty array")
                                                else:
                                                    # Ultimate fallback: just find next newline from activities_start
                                                    next_newline_fallback = raw_data.find('\n', activities_start)
                                                    if next_newline_fallback != -1:
                                                        raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_newline_fallback:]
                                                        logger.info(f"🔍 Removed malformed activities field using fallback newline search, set to empty array")
                                            
                                            logger.debug(f"🔍 After replacement preview: ...{raw_data[max(0, activities_start-30):activities_start+80]}...")
                                            logger.debug(f"🔍 Full JSON after replacement ends with: ...{raw_data[-100:]}")
                                        
                                        # Additional check: if there's still malformed data after our replacement, clean it up
                                        # Look for patterns that indicate leftover activities data
                                        check_pos = raw_data.find('"activities": []', activities_start)
                                        if check_pos != -1:
                                            after_replacement = raw_data[check_pos + len('"activities": []'):check_pos + len('"activities": []') + 100]
                                            # If we see patterns like }, { or }] or "=> that suggest leftover activities data
                                            if '}, {' in after_replacement or '}]' in after_replacement or '"=>' in after_replacement:
                                                # Find the next newline after our replacement
                                                cleanup_newline = raw_data.find('\n', check_pos + len('"activities": []'))
                                                if cleanup_newline != -1:
                                                    # Replace everything from activities_start to the newline
                                                    raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[cleanup_newline:]
                                                    logger.info(f"🔍 Cleaned up leftover activities data after replacement")
                                                    logger.debug(f"🔍 After cleanup preview: ...{raw_data[max(0, activities_start-30):activities_start+80]}...")
                                        
                                        # Additional fallback: if the character-by-character scan didn't work correctly,
                                        # look for the newline that should come after the activities field
                                        # The activities field is the last field, so it should be followed by \n}
                                        # This is more reliable than trying to find the closing quote
                                        if '"activities": []' in raw_data[activities_start:activities_start+20]:
                                            # Check if there's still malformed data after our replacement
                                            # Look for the pattern that indicates leftover activities data
                                            check_pos = raw_data.find('"activities": []', activities_start)
                                            if check_pos != -1:
                                                after_replacement = raw_data[check_pos + len('"activities": []'):check_pos + len('"activities": []') + 50]
                                                # If we see patterns like }, { or }] that suggest leftover activities data
                                                if '}, {' in after_replacement or '}]' in after_replacement or '"=>' in after_replacement:
                                                    # Find the next newline after our replacement
                                                    next_newline = raw_data.find('\n', check_pos + len('"activities": []'))
                                                    if next_newline != -1:
                                                        # Replace everything from activities_start to the newline
                                                        raw_data = raw_data[:activities_start] + '"activities": []' + raw_data[next_newline:]
                                                        logger.info(f"🔍 Fixed activities field replacement - removed leftover data")
                                                        logger.debug(f"🔍 After fix preview: ...{raw_data[max(0, activities_start-30):activities_start+80]}...")
                
                # Try to parse the fixed JSON
                try:
                    data = json.loads(raw_data)
                    logger.info(f"🔍 DEBUG: Manually parsed JSON data successfully")
                    logger.debug(f"🔍 Parsed data keys: {list(data.keys()) if data else 'None'}")
                    # Data is successfully parsed, continue with normal processing
                except json.JSONDecodeError as final_error:
                    logger.error(f"❌ Final JSON parse failed after activities fix: {final_error}")
                    logger.error(f"❌ Raw data around error (char {final_error.pos}): ...{raw_data[max(0, final_error.pos-50):final_error.pos+50]}...")
                    # Re-raise to be caught by outer exception handler
                    raise
            except Exception as manual_parse_error:
                logger.error(f"❌ JSON parsing error (both standard and manual failed): {json_error}")
                logger.error(f"   Manual parse error: {manual_parse_error}")
                logger.error(f"   Raw data preview: {request.get_data(as_text=True)[:500]}")
                # Try to continue anyway - extract what we can and set activities to empty
                try:
                    # Try to extract at least the contact_email which is critical
                    raw_text = request.get_data(as_text=True)
                    email_match = re.search(r'"contact_email"\s*:\s*"([^"]+)"', raw_text)
                    if email_match:
                        logger.warning("⚠️ Using fallback parsing - activities will be empty")
                        # Create minimal data structure
                        data = {'contact_email': email_match.group(1), 'activities': []}
                        # Try to extract other fields
                        for field in ['contact_name', 'account_name', 'account_id']:
                            field_match = re.search(f'"{field}"\\s*:\\s*"([^"]+)"', raw_text)
                            if field_match:
                                data[field] = field_match.group(1)
                    else:
                        raise ValueError("Could not extract contact_email")
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback parsing also failed: {fallback_error}")
                    return jsonify({
                        "status": "error",
                        "message": f"Invalid JSON format: {str(json_error)}. Please check your Workato request format.",
                        "timestamp": datetime.datetime.now().isoformat()
                    }), 400
                # If fallback parsing succeeded, continue with the extracted data
        
        # Check if data was successfully parsed
        # Note: 'data' should be set either by request.get_json() or by manual parsing
        if 'data' not in locals():
            logger.error(f"❌ Data variable not defined after parsing attempts")
            return jsonify({
                "status": "error",
                "message": "No JSON data provided or parsing failed",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        if not data:
            logger.warning(f"⚠️ Data is empty or None after parsing. Data type: {type(data)}, Data value: {data}")
            return jsonify({
                "status": "error",
                "message": "No JSON data provided",
                "timestamp": datetime.datetime.now().isoformat()
            }), 400
        
        logger.info(f"✅ Data successfully parsed. Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
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
            campaign_name="MSS Signed But Not Activated Campaign",
            version_endpoint='/api/workato/send-new-email'
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

def log_dump_to_automation_logs(gc, spreadsheet_id, record_count):
    """
    Log dump execution to Automation Logs tab.
    
    Args:
        gc: gspread client
        spreadsheet_id: Google Sheet ID
        record_count: Number of records dumped
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        log_sheet_name = 'Automation Logs'
        
        # Get or create Automation Logs worksheet
        try:
            log_worksheet = spreadsheet.worksheet(log_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Create worksheet if it doesn't exist
            log_worksheet = spreadsheet.add_worksheet(title=log_sheet_name, rows=1000, cols=10)
            # Add headers if it's a new sheet
            log_worksheet.update('A1:D1', [['Timestamp', 'Status', 'Records Dumped', 'Notes']])
            # Format header row
            log_worksheet.format('A1:D1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
        
        # Get current timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Prepare log entry
        log_entry = [
            timestamp,
            'Success',
            record_count,
            f'Daily dump completed - {record_count} email records'
        ]
        
        # Append to the sheet (get next available row)
        try:
            # Get all values to find next row
            all_values = log_worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            # If sheet is empty except headers, start at row 2
            if len(all_values) <= 1:
                next_row = 2
            
            # Append the log entry
            log_worksheet.append_row(log_entry)
            
            logger.info(f"✅ Logged dump execution to Automation Logs: {timestamp}")
            return True, f"Logged to Automation Logs"
        except Exception as e:
            logger.error(f"❌ Error appending to Automation Logs: {e}")
            return False, str(e)
        
    except Exception as e:
        logger.error(f"❌ Error logging to Automation Logs: {e}")
        return False, str(e)

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
                'created_at': 'Created At',
                'sfdc_task_id': 'SFDC Task ID',
                'status': 'Status'
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
        
        # Log to Automation Logs tab
        log_success, log_message = log_dump_to_automation_logs(gc, spreadsheet_id, len(records))
        if not log_success:
            logger.warning(f"⚠️ Failed to log to Automation Logs: {log_message}")
        else:
            logger.info(f"✅ {log_message}")
        
        return True, f"Successfully wrote {len(records)} records to {sheet_name}"
        
    except Exception as e:
        logger.error(f"❌ Error writing to Google Sheets: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}"

@app.route('/api/workato/check-non-campaign-emails', methods=['POST'])
def workato_check_non_campaign_emails():
    """
    Check emails from the last 24 hours and auto-reply to senders not in the campaign contact list.
    The provided contacts list represents campaign members. Non-campaign senders are directed to merchantcare@affirm.com.
    
    Expected input format:
    {
        "contacts": [
            {"email": "contact1@example.com"},
            {"email": "contact2@example.com"},
            ...
        ]
    }
    Or simpler format:
    {
        "contacts": ["contact1@example.com", "contact2@example.com", ...]
    }
    """
    try:
        import time
        
        data = request.get_json() if request.is_json else {}
        
        if not data or 'contacts' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required "contacts" parameter. Expected format: {"contacts": ["email1@example.com", "email2@example.com"]}',
                'timestamp': datetime.datetime.now().isoformat()
            }), 400
        
        contacts = data.get('contacts', [])
        if not isinstance(contacts, list):
            return jsonify({
                'status': 'error',
                'message': 'Contacts must be a list of email addresses',
                'timestamp': datetime.datetime.now().isoformat()
            }), 400
        
        # Normalize and extract emails from campaign contacts list
        # Handle both formats: ["email@example.com"] or [{"email": "email@example.com"}]
        campaign_emails = set()
        for contact in contacts:
            if isinstance(contact, str):
                email = contact
            elif isinstance(contact, dict):
                email = contact.get('email', '')
            else:
                continue
            
            if email:
                normalized = normalize_email(email)
                campaign_emails.add(normalized)
                # Also add the original email (lowercased) for matching
                campaign_emails.add(email.lower().strip())
        
        logger.info(f"📋 Processing non-campaign email check with {len(campaign_emails)} campaign contacts")
        logger.info(f"📋 Campaign emails: {', '.join(sorted(campaign_emails))}")
        
        # Authenticate Gmail
        creds = authenticate_gmail()
        service = build('gmail', 'v1', credentials=creds)
        
        # Calculate timestamp for 24 hours ago
        current_time_ms = int(time.time() * 1000)
        twenty_four_hours_ago_ms = current_time_ms - (24 * 60 * 60 * 1000)
        
        # Query for emails from the last 24 hours
        # Use Gmail search query: after:timestamp
        query = f'after:{twenty_four_hours_ago_ms // 1000}'
        logger.info(f"🔍 Searching for emails in INBOX from last 24 hours (after {datetime.datetime.fromtimestamp(twenty_four_hours_ago_ms / 1000)})")
        
        results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX'],
            q=query,
            maxResults=500
        ).execute()
        
        messages = results.get('messages', [])
        logger.info(f"📧 Found {len(messages)} emails in INBOX from last 24 hours")
        
        non_campaign_emails = []
        processed_threads = set()  # Track threads we've already replied to
        
        for msg in messages:
            try:
                msg_id = msg['id']
                message = service.users().messages().get(userId='me', id=msg_id).execute()
                thread_id = message.get('threadId')
                
                # Skip if we've already processed this thread
                if thread_id and thread_id in processed_threads:
                    continue
                
                # Extract email details
                headers = message['payload'].get('headers', [])
                sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                # Extract and normalize sender email
                sender_email = normalize_email(sender)
                sender_email_original = sender.lower()
                if '<' in sender_email_original and '>' in sender_email_original:
                    sender_email_original = sender_email_original.split('<')[1].split('>')[0]
                
                # Check if sender is in campaign list (check both normalized and original)
                is_campaign_member = (
                    sender_email in campaign_emails or
                    sender_email_original in campaign_emails or
                    sender_email_original.lower() in campaign_emails
                )
                
                # Also check if it's from us (Jake Morgan) - we should skip those
                jake_email = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com').lower()
                is_from_us = (
                    'jake.morgan@affirm.com' in sender.lower() or
                    jake_email in sender.lower() or
                    normalize_email(jake_email) == sender_email
                )
                
                # Skip if campaign member or from us
                if is_campaign_member or is_from_us:
                    continue
                
                # For non-campaign emails, check if the latest message in the thread is from them (not us)
                # Only respond if the latest message is from the non-campaign sender
                if thread_id:
                    try:
                        # Get all messages in the thread to find the latest one
                        thread_data = service.users().threads().get(userId='me', id=thread_id).execute()
                        thread_messages = thread_data.get('messages', [])
                        
                        if thread_messages:
                            # Get the latest message in the thread
                            latest_thread_msg_id = thread_messages[-1]['id']
                            latest_thread_msg = service.users().messages().get(userId='me', id=latest_thread_msg_id).execute()
                            latest_thread_labels = latest_thread_msg.get('labelIds', [])
                            latest_thread_headers = latest_thread_msg['payload'].get('headers', [])
                            latest_thread_sender = next((h['value'] for h in latest_thread_headers if h['name'] == 'From'), '')
                            
                            # Check if latest message is from us (Jake Morgan)
                            jake_email = os.getenv('EMAIL_USERNAME', 'jake.morgan@affirm.com').lower()
                            latest_is_from_us = (
                                'SENT' in latest_thread_labels or
                                'jake.morgan@affirm.com' in latest_thread_sender.lower() or
                                jake_email in latest_thread_sender.lower()
                            )
                            
                            if latest_is_from_us:
                                logger.info(f"⏭️ Skipping thread {thread_id} from {sender_email_original} - latest message is from us (Jake Morgan)")
                                processed_threads.add(thread_id)
                                continue
                            else:
                                logger.info(f"✅ Latest message in thread {thread_id} is from {sender_email_original} - will respond")
                        else:
                            # No thread messages found, use the current message
                            logger.info(f"⚠️ Thread {thread_id} has no messages, using current message")
                    except Exception as thread_check_error:
                        logger.warning(f"⚠️ Error checking thread {thread_id} for latest message: {thread_check_error}")
                        # If we can't check the thread, proceed with the current message
                        logger.info(f"Proceeding with current message {msg_id} from {sender_email_original}")
                
                # This is a non-campaign sender - add to list and send auto-reply
                non_campaign_emails.append({
                    'id': msg_id,
                    'threadId': thread_id,
                    'sender': sender,
                    'sender_email': sender_email_original,
                    'subject': subject,
                    'date': date
                })
                
                # Extract email body for context
                email_body = extract_email_body(message['payload'])
                
                # Get non-campaign email prompt from database or use default
                non_campaign_prompt = None
                if DB_AVAILABLE:
                    try:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute('''
                                SELECT prompt_content
                                FROM prompt_versions
                                WHERE prompt_type = 'non-campaign-email' AND version_letter = 'DEFAULT'
                            ''')
                            row = cursor.fetchone()
                            if row:
                                non_campaign_prompt = row[0]
                            conn.close()
                    except Exception as e:
                        logger.warning(f"Could not load non-campaign email prompt from database: {e}")
                
                # Fall back to environment variable or default
                if not non_campaign_prompt:
                    non_campaign_prompt = os.getenv('NON_CAMPAIGN_EMAIL_PROMPT_TEMPLATE')
                
                # Generate AI response using the non-campaign email prompt
                try:
                    sender_name = sender.split('<')[0].strip() if '<' in sender else sender_email_original.split('@')[0].capitalize()
                    if not sender_name or sender_name == sender_email_original:
                        sender_name = "there"
                    
                    logger.info(f"🤖 Generating AI response for non-campaign email from {sender_email_original}")
                    ai_response = generate_ai_response(
                        email_body=email_body,
                        sender_name=sender_name,
                        recipient_name="Jake Morgan",
                        conversation_history=None,
                        prompt_template=non_campaign_prompt
                    )
                    logger.info(f"✅ AI response generated for non-campaign email from {sender_email_original}")
                    
                    # Send auto-reply with AI-generated content
                    email_result = send_threaded_email_reply(
                        to_email=sender_email_original,
                        subject=subject,
                        reply_content=ai_response,
                        original_message_id=msg_id,
                        sender_name="Jake Morgan",
                        cc_recipients=None
                    )
                    
                    if isinstance(email_result, dict) and email_result.get('status') == 'success':
                        logger.info(f"✅ Sent AI-generated auto-reply to non-campaign sender {sender_email_original} (thread {thread_id})")
                        if thread_id:
                            processed_threads.add(thread_id)
                    else:
                        logger.warning(f"⚠️ Failed to send auto-reply to {sender_email_original}: {email_result}")
                        
                except Exception as reply_error:
                    logger.error(f"❌ Error generating or sending AI reply to {sender_email_original}: {reply_error}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Continue processing other emails even if one fails
                
            except Exception as e:
                logger.error(f"❌ Error processing message {msg.get('id', 'unknown')}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        logger.info(f"📊 Summary: Found {len(non_campaign_emails)} non-campaign emails, sent {len(processed_threads)} auto-replies")
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(messages)} emails from last 24 hours. Found {len(non_campaign_emails)} non-campaign senders and sent {len(processed_threads)} auto-replies.',
            'total_emails_checked': len(messages),
            'non_campaign_count': len(non_campaign_emails),
            'replies_sent': len(processed_threads),
            'non_campaign_emails': [
                {
                    'sender': email['sender'],
                    'sender_email': email['sender_email'],
                    'subject': email['subject'],
                    'date': email['date']
                }
                for email in non_campaign_emails
            ],
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error in check-non-campaign-emails endpoint: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f'Error processing non-campaign emails: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

@app.route('/api/workato/update-sfdc-task-id', methods=['POST'])
def workato_update_sfdc_task_id():
    """
    Workato endpoint to update SFDC Task ID for a tracking ID.
    
    Expected input format:
    {
        "tracking_id": "abc-123-def-456",
        "sfdc_task_id": "00TVB00000EbjuB2AR"
    }
    
    Returns:
    {
        "status": "success",
        "message": "SFDC Task ID updated successfully",
        "tracking_id": "abc-123-def-456",
        "sfdc_task_id": "00TVB00000EbjuB2AR"
    }
    """
    try:
        if not DB_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Database not available',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        # Try to get JSON data, with better error handling
        data = {}
        try:
            if request.is_json:
                data = request.get_json(force=True) or {}
            elif request.content_type and 'application/json' in request.content_type:
                data = request.get_json(force=True) or {}
            else:
                # Try to get from form data or args as fallback
                data = {
                    'tracking_id': request.form.get('tracking_id') or request.args.get('tracking_id', ''),
                    'sfdc_task_id': request.form.get('sfdc_task_id') or request.args.get('sfdc_task_id', '')
                }
        except Exception as json_error:
            logger.error(f"❌ JSON parsing error: {json_error}")
            # Try to get raw data and parse manually
            try:
                import json
                raw_data = request.get_data(as_text=True)
                if raw_data:
                    data = json.loads(raw_data)
                else:
                    data = {}
            except Exception as parse_error:
                logger.error(f"❌ Failed to parse request data: {parse_error}")
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid request format. Expected JSON with tracking_id and sfdc_task_id. Error: {str(parse_error)}',
                    'timestamp': datetime.datetime.now().isoformat()
                }), 400
        
        # Log received data for debugging
        logger.info(f"📥 Received request data: {data}")
        logger.info(f"📥 Request content type: {request.content_type}")
        logger.info(f"📥 Request method: {request.method}")
        
        # Validate input
        tracking_id = str(data.get('tracking_id', '')).strip() if data.get('tracking_id') else ''
        sfdc_task_id = str(data.get('sfdc_task_id', '')).strip() if data.get('sfdc_task_id') else ''
        
        # If tracking_id is missing, skip processing and return success
        if not tracking_id:
            logger.info(f"⏭️ Skipping update - no tracking_id provided. Received data: {data}")
            return jsonify({
                'status': 'success',
                'message': 'Skipped - no tracking_id provided',
                'skipped': True,
                'timestamp': datetime.datetime.now().isoformat()
            }), 200
        
        # If sfdc_task_id is missing, skip processing and return success
        if not sfdc_task_id:
            logger.info(f"⏭️ Skipping update - no sfdc_task_id provided. Tracking ID: {tracking_id}")
            return jsonify({
                'status': 'success',
                'message': 'Skipped - no sfdc_task_id provided',
                'skipped': True,
                'tracking_id': tracking_id,
                'timestamp': datetime.datetime.now().isoformat()
            }), 200
        
        logger.info(f"📝 Updating SFDC Task ID for tracking_id: {tracking_id} -> {sfdc_task_id}")
        
        # Connect to database
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'status': 'error',
                'message': 'Database connection failed',
                'timestamp': datetime.datetime.now().isoformat()
            }), 503
        
        cursor = conn.cursor()
        
        # Check if tracking_id exists
        cursor.execute('SELECT id, recipient_email, subject FROM email_tracking WHERE tracking_id = %s', (tracking_id,))
        email_record = cursor.fetchone()
        
        if not email_record:
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Tracking ID not found: {tracking_id}',
                'timestamp': datetime.datetime.now().isoformat()
            }), 404
        
        # Update the SFDC Task ID
        cursor.execute('''
            UPDATE email_tracking
            SET sfdc_task_id = %s
            WHERE tracking_id = %s
        ''', (sfdc_task_id, tracking_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Successfully updated SFDC Task ID for tracking_id: {tracking_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'SFDC Task ID updated successfully',
            'tracking_id': tracking_id,
            'sfdc_task_id': sfdc_task_id,
            'recipient_email': email_record[1],
            'subject': email_record[2],
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Error updating SFDC Task ID: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Error updating SFDC Task ID: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

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
                created_at,
                sfdc_task_id
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
        
        # Ensure records are sorted by sent_at in descending order (most recent first)
        # This ensures proper ordering even if database query order is not preserved
        if records:
            def get_sent_at(record):
                sent_at = record.get('sent_at', '')
                # Handle both ISO format strings and datetime objects
                if isinstance(sent_at, str):
                    try:
                        return datetime.datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        return datetime.datetime.min
                elif isinstance(sent_at, datetime.datetime):
                    return sent_at
                return datetime.datetime.min
            
            records.sort(key=get_sent_at, reverse=True)
            logger.info(f"📊 Sorted {len(records)} records by sent_at (descending)")
        
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
