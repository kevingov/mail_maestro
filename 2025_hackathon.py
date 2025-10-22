import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from markupsafe import Markup
from flask_bootstrap import Bootstrap
# from flask_datepicker import datepicker
# from flask_table import Table, Col
import json
# from flask_wtf import Form
# from wtforms import DateField, validators
# from wtforms.fields import DateField
from datetime import date, time, datetime, timedelta
import os
import pandas as pd
import numpy as np
import datetime
from decimal import Decimal, ROUND_HALF_UP
import decimal
import locale
import plotly.graph_objects as go
import plotly.io as pio
import plotly.offline
from plotly.offline import plot
import plotly.express as px
from plotly.subplots import make_subplots
from openai import OpenAI
import re


import plot

from simple_salesforce import Salesforce
import dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import openai
import base64
import email
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pandas as pd


# Load environment variables
dotenv.load_dotenv()

app = Flask(__name__)
Bootstrap(app)



SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY

client = OpenAI()


# Salesforce Authentication
sf = Salesforce(username=os.getenv("SF_USERNAME"),
                password=os.getenv("SF_PASSWORD"),
                security_token=os.getenv("SF_SECURITY_TOKEN"),
                domain=os.getenv("SF_DOMAIN"))


# SMTP Email Configuration
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


locale.setlocale( locale.LC_ALL, 'en_CA.UTF-8' )
TWOPLACES = Decimal(10) ** -2 

# This is the Gmail Authenication Portion
SCOPES = [ 
    'https://www.googleapis.com/auth/gmail.readonly',  # ✅ Read emails
    'https://www.googleapis.com/auth/gmail.send',      # ✅ Send emails
    'https://www.googleapis.com/auth/gmail.modify'     # ✅ Mark emails as read, move emails
    ]


# ✅ **Affirm’s Voice & Branding Guidelines**
AFFIRM_VOICE_GUIDELINES = """
As an AI-powered business development assistant at Affirm, your tone must strictly follow Affirm’s brand voice:

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

def authenticate_gmail():
    creds = None
    # Load token from file if exists
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If no valid creds, go through authentication
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the creds for next time
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

# 🔹 Fetch salesforce contacts from accounts that are owned by user and have Self_Service__c = true
def fetch_salesforce_accounts():
    """
    Fetch contact email addresses from Salesforce where:
    1. Contact is from an Account owned by current user
    2. Account has Self_Service__c = true
    3. Contact has Primary_Affirm_Point_of_Contact__c = true
    4. Contact has Email
    """
    try:
        # Get the authenticated user using the username from env vars (more reliable)
        sf_username = os.getenv("SF_USERNAME")
        user_info = sf.query("SELECT Id, Name FROM User WHERE Username = '{}'".format(sf_username))
        if not user_info["records"]:
            print("❌ Could not get current user info for fetching accounts")
            return {}
        
        current_user = user_info["records"][0]
        user_id = current_user["Id"]
        print(f"👤 Current User: {current_user["Name"]} (ID: {user_id})")
        
        # Query contacts through their related accounts
        query = f"""
        SELECT Id, Name, Email, AccountId, Account.Name, Account.Self_Service__c, 
               Account.OwnerId, Account.Owner.Name, Primary_Affirm_Point_of_Contact__c
        FROM Contact 
        WHERE Account.OwnerId = "{user_id}" 
        AND Account.Self_Service__c = true 
        AND Primary_Affirm_Point_of_Contact__c = true 
        AND Email != NULL
        """
        
        print(f"🔍 Querying contacts from Self-Service accounts owned by {current_user["Name"]}...")
        contacts = sf.query(query)["records"]
        
        # Build contact emails dictionary (email -> contact_id)
        contact_emails = {}
        for contact in contacts:
            if contact["Email"] and contact["Email"].strip():
                contact_emails[contact["Email"].strip().lower()] = contact["Id"]
        
        print(f"📌 Found {len(contact_emails)} contacts matching criteria:")
        print(f"   - From accounts owned by: {current_user["Name"]}")
        print(f"   - Account Self-Service: Yes")
        print(f"   - Contact Primary Affirm Point: Yes")
        print(f"   - Contact has email: Yes")
        
        # Show sample contacts with account info
        if contact_emails:
            print("\n📋 Sample contacts:")
            for i, contact in enumerate(contacts[:5], 1):
                print(f"  {i}. {contact["Name"]} ({contact["Email"]})")
                print(f"     Account: {contact["Account"]["Name"]} (Self-Service: {contact["Account"]["Self_Service__c"]})")
                print()
        
        return contact_emails
    except Exception as e:
        print(f"❌ Error fetching Salesforce contacts: {e}")
        return {}  # ✅ Return empty dictionary instead of None

# 🔹 Fetch accounts that are owned by user and have Self_Service__c = true
def fetch_my_self_service_accounts():
    """
    Fetch accounts from Salesforce where:
    1. Account is owned by current user
    2. Account has Self_Service__c = true
    """
    try:
        # Get the authenticated user using the username from env vars (more reliable)
        sf_username = os.getenv("SF_USERNAME")
        user_info = sf.query("SELECT Id, Name FROM User WHERE Username = '{}'".format(sf_username))
        if not user_info["records"]:
            print("❌ Could not get current user info")
            return []
        
        current_user = user_info["records"][0]
        user_id = current_user["Id"]
        print(f"👤 Current User: {current_user['Name']} (ID: {user_id})")
        
        # Query accounts directly (fixed formatting)
        query = f"SELECT Id, Name, Self_Service__c, OwnerId, Owner.Name, Industry, Website, LastActivityDate, CreatedDate, mo_Email__c FROM Account WHERE OwnerId = '{user_id}' AND Self_Service__c = true"
        
        print(f"🔍 Querying Self-Service accounts owned by {current_user['Name']}...")
        accounts = sf.query(query)["records"]
        
        print(f"📌 Found {len(accounts)} Self-Service accounts:")
        print(f"   - Owned by: {current_user['Name']}")
        print(f"   - Self-Service flag: Yes")
        
        # Show sample accounts
        if accounts:
            print("\n📋 Sample accounts:")
            for i, account in enumerate(accounts[:5], 1):
                print(f"  {i}. {account['Name']} (ID: {account['Id']})")
                print(f"     Industry: {account.get('Industry', 'N/A')}")
                print(f"     Website: {account.get('Website', 'N/A')}")
                print(f"     Email: {account.get('mo_Email__c', 'N/A')}")
                print()
        
        return accounts
    except Exception as e:
        print(f"❌ Error fetching Self-Service accounts: {e}")
        return []  # ✅ Return empty list instead of None

def extract_email(sender_str):
    """
    Extracts just the email address from a 'Name <email@example.com>' format.
    """
    match = re.search(r'<(.*?)>', sender_str)
    return match.group(1) if match else sender_str  # Returns email or full string if no match

def extract_email_body(payload):
    """
    Extracts the body of an email, handling both plain text and HTML.
    """
    body = ""

    # ✅ Case 1: If the email has multiple parts (HTML, plain text, etc.)
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part['mimeType']
            body_data = part.get('body', {}).get('data')

            if body_data:
                decoded_body = base64.urlsafe_b64decode(body_data).decode("utf-8")

                # ✅ Prefer plain text over HTML
                if mime_type == 'text/plain':
                    return decoded_body  # ✅ Return first plain text body found
                elif mime_type == 'text/html':
                    body = decoded_body  # ✅ Store HTML if no plain text is found

    # ✅ Case 2: If there are no 'parts' (single body email)
    elif 'body' in payload:
        body_data = payload['body'].get('data')
        if body_data:
            body = base64.urlsafe_b64decode(body_data).decode("utf-8")

    return body.strip()  # ✅ Ensure no extra spaces

# 🔹 Fetch unread emails from Gmail
def get_all_emails():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    print("✅ Connected to Gmail API")

    # Get Salesforce contacts using the working function
    salesforce_contacts = fetch_my_account_contacts()
    print(f"📌 Fetched {len(salesforce_contacts)} Salesforce contacts")

    # Create a lookup dictionary for email addresses
    salesforce_emails = {}
    for contact in salesforce_contacts:
        if contact.get('Email'):
            salesforce_emails[contact['Email'].lower()] = {
                'contact_id': contact['Id'],
                'account_id': contact.get('AccountId'),
                'contact_name': contact.get('Name')
            }

    # Fetch ALL emails from inbox (not just unread)
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=100).execute()
    messages = results.get('messages', [])
    if not messages:
        print("⚠️ No emails found in inbox!")
        return []

    print(f"📬 Found {len(messages)} total emails in inbox")

    emails = []
    for msg in messages:
        msg_id = msg['id']
        email_data = service.users().messages().get(userId='me', id=msg_id).execute()
        msg_payload = email_data['payload']
        headers = msg_payload['headers']

        sender = next(h['value'] for h in headers if h['name'] == 'From')
        sender_email = extract_email(sender).lower()  # Extract and normalize email
        subject = next(h['value'] for h in headers if h['name'] == 'Subject')

        # Decode the email body
        body = extract_email_body(msg_payload)

        # Check if this email has been replied to
        labels = email_data.get('labelIds', [])
        is_unread = 'UNREAD' in labels
        
        # Only add the email if the sender exists in Salesforce
        if sender_email in salesforce_emails:
            contact_info = salesforce_emails[sender_email]
            emails.append({
                'id': msg_id,
                'threadId': email_data.get('threadId'),  # Add threadId
                'sender': sender_email,
                'subject': subject,
                'body': body,
                'salesforce_id': contact_info['contact_id'],
                'account_id': contact_info['account_id'],
                'contact_name': contact_info['contact_name'],
                'is_unread': is_unread,
                'labels': labels
            })
        else:
            print(f"⚠️ Email from {sender_email} does not match any Salesforce contact")

    print(f"✅ Found {len(emails)} emails from Salesforce contacts")
    return emails


def has_been_replied_to(email_id, service):
    """
    Check if the LATEST message in the thread is from us (Jake Morgan).
    If the latest message is from us, we've already replied.
    If the latest message is from someone else, we need to reply.
    """
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
        
        if is_from_us:
            print(f"✅ Latest message in thread is from us: {sender}")
        else:
            print(f"📧 Latest message in thread is from: {sender} - needs reply")
            
        return is_from_us
        
    except Exception as e:
        print(f"❌ Error checking reply status for email {email_id}: {e}")
        return False

# 🔹 Get emails that need replies (from Salesforce contacts, not yet replied to)
def get_emails_needing_replies():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    print("✅ Connected to Gmail API")

    # Get all emails from Salesforce contacts
    all_emails = get_all_emails()
    
    if not all_emails:
        print("⚠️ No emails from Salesforce contacts found!")
        return []

    # Group emails by conversation thread (threadId)
    thread_emails = {}
    for email in all_emails:
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
            print(f"📧 Conversation thread {thread_id} from {latest_email['sender']} needs a reply")
        else:
            print(f"✅ Conversation thread {thread_id} from {latest_email['sender']} already has a reply")

    print(f"📬 Found {len(emails_needing_replies)} conversation threads needing replies")
    return emails_needing_replies



# 🔹 Use AI to Generate Smart Responses
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
        print(f"❌ Error generating AI response: {e}")
        fallback_response = f"Hi {recipient_name},\n\nThank you for your message. I'll be happy to help you with any questions about Affirm.\n\nBest regards,\n{sender_name}"
    return format_pardot_email(first_name=recipient_name, 
                                   email_content=fallback_response, 
                               recipient_email="recipient@email.com", 
                               sender_name=sender_name)

# 🔹 Send AI-Generated Email Replies with Tracking
def send_email_reply(to_email, subject, html_body, campaign_name="AI Reply", base_url="https://web-production-6dfbd.up.railway.app"):
    try:
        from email_tracker import EmailTracker
        
        # Initialize email tracker
        tracker = EmailTracker()
        
        # Track the email reply
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=EMAIL_USERNAME,
            subject=f"Re: {subject}",
            campaign_name=campaign_name
        )
        
        # Add tracking pixel to email content
        tracked_html_body = tracker.add_tracking_to_email(html_body, tracking_id, base_url)
        
        creds = authenticate_gmail()
        service = build('gmail', 'v1', credentials=creds)

        print(f"📩 Preparing to send tracked reply to {to_email} with subject: {subject}")
        print(f"🔍 Tracking ID: {tracking_id}")

        message = MIMEMultipart()
        message["to"] = to_email
        message["subject"] = f"Re: {subject}"
        message.attach(MIMEText(tracked_html_body, "html"))

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        message_body = {'raw': raw_message}

        response = None  # ✅ Define response outside try block
        
        response = service.users().messages().send(userId='me', body=message_body).execute()
        print("✅ Tracked email successfully sent! Response:", response)  # ✅ Debug API response
        return {
            'status': f"✅ Reply sent to {to_email}",
            'tracking_id': tracking_id,
            'tracking_url': f"{base_url}/tracking/details/{tracking_id}"
        }
    except Exception as e:
        print(f"❌ Error sending email to {to_email}: {str(e)}")  # ✅ Debug errors
        return {
            'status': f"❌ Error sending email to {to_email}: {str(e)}",
            'tracking_id': None,
            'tracking_url': None
        }


# 🔹 Log Email Reply in Salesforce
def log_salesforce_reply(email):
    """
    Log an email reply in Salesforce, attaching it to the relevant account.
    """
    # Use account_id for WhatId field (Task must be related to Account, not Contact)
    what_id = email.get('account_id') or email.get('salesforce_id')
    if what_id:
        sf.Task.create({
        'Subject': f"Email Reply from {email['sender']}",
        'Description': f"Subject: {email['subject']}\n\nMessage: {email['body']}",
        'Status': 'Completed',
        'Priority': 'Normal',
            'WhatId': what_id  # Attach to Salesforce Account
    })
    else:
        print(f"⚠️ No account_id or salesforce_id found for email from {email['sender']}")

# This is the salesforce portion

# 🔹 Function: Fetch Inactive Merchants from Salesforce
def fetch_merchants():
    # Get all fields from the Account object
    account_fields = [field['name'] for field in sf.Account.describe()['fields']]

    # Convert field list to a string for query
    account_fields_str = ", ".join(account_fields)

    # Query all fields from Account
    query = f"SELECT {account_fields_str} FROM Account"
    df = sf.query(query)

    # Print output
    print(df)

    # Convert to DataFrame
    df = pd.DataFrame(df['records']).drop(columns='attributes')
    return df

    # WHERE LastActivityDate < LAST_N_DAYS:30

# 🔹 Function: Generate AI-Powered Outreach Message for new messages

    # Example format:
    # - Greeting (e.g., "Hello {merchant_name},") **(New Line)**
    # - Introduction about Affirm & its benefits **(New Line)**
    # - Why this business specifically benefits from Affirm **(New Line)**
    # - Call to Action with a phone number **(New Line)**
    # - Closing statement **(New Line)**
        
def generate_message(merchant_name, last_activity, merchant_industry, merchant_website, sender_name, account_description="", account_revenue=0, account_employees=0, account_location="", contact_title="", account_gmv=0):
    """
    Creates an Affirm-branded outreach email using AI with detailed Salesforce data.
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
        print(f"❌ Error generating AI response: {e}")
        return f"Hi {merchant_name}, Let's Connect!", "Let's connect to discuss how Affirm can benefit your business."
        
    # # response.choices[0].message.content.strip()
    # return format_pardot_email(first_name=merchant_name, 
    #                            email_content=response_text, 
    #                            recipient_email="recipient@email.com", 
    #                            sender_name=sender_name)

# 🔹 Function: Send Email via SMTP with Enhanced Security
def send_email(to_email, merchant_name, subject_line, email_content, campaign_name=None, base_url="https://web-production-6dfbd.up.railway.app"):
    try:
        from email_tracker import EmailTracker
        import time
        import random
        
        # Initialize email tracker
        tracker = EmailTracker()
        
        # Track the email and get tracking ID
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=EMAIL_USERNAME,
            subject=subject_line,
            campaign_name=campaign_name
        )
        
        # Add tracking pixel to email content
        tracked_email_content = tracker.add_tracking_to_email(email_content, tracking_id, base_url)
        
        # Create email message with enhanced headers
        msg = MIMEMultipart()
        
        # Enhanced email headers for Affirm email (UPDATED)
        msg["From"] = f"Jake Morgan - Affirm <{EMAIL_USERNAME}>"
        msg["To"] = to_email
        msg["Subject"] = subject_line
        msg["Reply-To"] = EMAIL_USERNAME
        msg["Return-Path"] = EMAIL_USERNAME
        msg["Message-ID"] = f"<{tracking_id}@affirm.com>"
        msg["X-Mailer"] = "Affirm Business Development"
        msg["X-Priority"] = "3"
        msg["X-MSMail-Priority"] = "Normal"
        msg["Importance"] = "Normal"
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@affirm.com?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        
        # Add Affirm-specific headers
        msg["X-Affirm-Campaign"] = campaign_name or "Business Outreach"
        msg["X-Affirm-Source"] = "Business Development"

        msg.attach(MIMEText(tracked_email_content, "html"))
        print(f"📧 Email with enhanced headers prepared for {to_email}")
        print(f"🔍 Tracking ID: {tracking_id}")

        # Add random delay to prevent bulk sending detection
        delay = random.uniform(2, 5)  # Random delay between 2-5 seconds
        print(f"⏱️ Waiting {delay:.1f} seconds before sending...")
        time.sleep(delay)

        # Send email via SMTP with enhanced security
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()  # Secure connection
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            
            # Set additional SMTP options for better deliverability
            server.ehlo()  # Identify ourselves to the server
            server.sendmail(EMAIL_USERNAME, to_email, msg.as_string())

        print(f"✅ Tracked email sent to {to_email}")
        return {
            'status': f"✅ Email sent to {to_email} with subject: {subject_line}",
            'tracking_id': tracking_id,
            'tracking_url': f"{base_url}/tracking/details/{tracking_id}"
        }

    except Exception as e:
        print(f"❌ Error sending email to {to_email}: {e}")
        return {
            'status': f"❌ Error sending email to {to_email}: {e}",
            'tracking_id': None,
            'tracking_url': None
        }


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




# 🔹 Function: Log Activity in Salesforce
def log_salesforce_activity(merchant_id, message):
    sf.Task.create({
        'Subject': 'Sent AI-Generated Outreach',
        'Description': message,
        'Status': 'Completed',
        'Priority': 'High',
        'WhatId': merchant_id
    })

def fetch_my_account_contacts():
    """
    Fetches contacts from accounts owned by the current user.
    Returns a list of contact dictionaries.
    """
    try:
        # Get the authenticated user using the username from env vars (more reliable)
        sf_username = os.getenv("SF_USERNAME")
        user_info = sf.query("SELECT Id, Name FROM User WHERE Username = '{}'".format(sf_username))
        if not user_info["records"]:
            print("❌ Could not get current user info for fetching contacts.")
            return []
        
        current_user = user_info["records"][0]
        user_id = current_user["Id"]
        print(f"👤 Current User: {current_user['Name']} (ID: {user_id})")

        # Enhanced query to get more detailed account and contact information including GMV
        query = f"SELECT Id, Name, Email, Phone, Title, AccountId, Account.Name, Account.Self_Service__c, Account.OwnerId, Account.Owner.Name, Account.Industry, Account.Website, Account.Description, Account.AnnualRevenue, Account.NumberOfEmployees, Account.BillingCity, Account.BillingState, Account.BillingCountry, Account.Trailing_12M_GMV__c, Primary_Affirm_Point_of_Contact__c FROM Contact WHERE Account.OwnerId = '{user_id}' AND Account.Self_Service__c = true AND Primary_Affirm_Point_of_Contact__c = true AND Email != NULL"
        
        print(f"🔍 Querying contacts from Self-Service accounts owned by {current_user['Name']}...")
        contacts = sf.query(query)["records"]
        
        print(f"📌 Found {len(contacts)} contacts matching criteria:")
        print(f"   - From accounts owned by: {current_user['Name']}")
        print(f"   - Account Self-Service: Yes")
        print(f"   - Contact Primary Affirm Point: Yes")
        print(f"   - Contact has email: Yes")

        if contacts:
            print("\n📋 Sample contacts:")
            for i, contact in enumerate(contacts[:5], 1):
                gmv_value = contact['Account'].get('Trailing_12M_GMV__c', 0) or 0
                gmv_display = f"${gmv_value:,.2f}" if gmv_value else "Not available"
                print(f"  {i}. {contact['Name']} (ID: {contact['Id']})")
                print(f"     Email: {contact.get('Email', 'N/A')}")
                print(f"     Phone: {contact.get('Phone', 'N/A')}")
                print(f"     Title: {contact.get('Title', 'N/A')}")
                print(f"     Account: {contact['Account']['Name']} (Self-Service: {contact['Account']['Self_Service__c']})")
                print(f"     Trailing 12M GMV: {gmv_display}")
                print()
        
        return contacts
    except Exception as e:
        print(f"❌ Error fetching contacts: {e}")
        return []

user_info = sf.query("SELECT Id, Name, Email FROM User LIMIT 1")
print(user_info)




@app.route('/send_new_email')
def send_new_email():
    # Get contacts from Self-Service accounts instead of all merchants
    contacts = fetch_my_account_contacts()
    results = []

    # Rate limiting: Only send to first 5 contacts to avoid spam detection
    max_emails = 5
    contacts_to_process = contacts[:max_emails]
    
    print(f"📧 Processing {len(contacts_to_process)} contacts (limited to {max_emails} to prevent spam)")

    for i, contact in enumerate(contacts_to_process):
        try:
            # Extract detailed contact and account information with null safety
            contact_name = contact["Name"]
            contact_email = contact["Email"]
            contact_title = contact.get("Title") or ""
            contact_phone = contact.get("Phone") or ""
            
            # Account information with null safety
            account_name = contact["Account"]["Name"]
            account_industry = contact["Account"].get("Industry") or "Business"
            account_website = contact["Account"].get("Website") or ""
            account_description = contact["Account"].get("Description") or ""
            account_revenue = contact["Account"].get("AnnualRevenue") or 0
            account_employees = contact["Account"].get("NumberOfEmployees") or 0
            account_city = contact["Account"].get("BillingCity") or ""
            account_state = contact["Account"].get("BillingState") or ""
            account_country = contact["Account"].get("BillingCountry") or ""
            account_id = contact["AccountId"]
            
            # Sender information (you can customize this)
            sender_name = "Jake Morgan"
            sender_title = "Business Development"
            sender_phone = "Your Phone Number"  # Add your phone if desired

            if not contact_email:
                print(f"⚠️ Skipping {contact_name} - no email address")
                continue  # Skip if no email

            print(f"📧 Sending email {i+1}/{len(contacts_to_process)} to {contact_name} ({contact_email})")
            print(f"   Account: {account_name} ({account_industry})")
            print(f"   Website: {account_website}")

            # Extract GMV data
            account_gmv = contact["Account"].get("Trailing_12M_GMV__c") or 0
            
            # ✅ Generate Subject Line & Email Content with AI using detailed info including GMV
            subject_line, email_content = generate_message(
                merchant_name=contact_name,
                last_activity="Recent",
                merchant_industry=account_industry,
                merchant_website=account_website,
                sender_name=sender_name,
                # Additional context for better personalization
                account_description=account_description,
                account_revenue=account_revenue,
                account_employees=account_employees,
                account_location=f"{account_city}, {account_state}".strip(", ") if account_city else "",
                contact_title=contact_title,
                account_gmv=account_gmv
            )

            # ✅ Ensure HTML email format
            formatted_email = format_pardot_email(
                first_name=contact_name,
                email_content=email_content,
                recipient_email=contact_email,
                sender_name=sender_name
            )

            # ✅ Send HTML Email with Tracking
            email_result = send_email(
                to_email=contact_email,
                merchant_name=contact_name,
                subject_line=subject_line,
                email_content=formatted_email,
                campaign_name="Self-Service Account Outreach"
            )
            email_status = email_result['status'] if isinstance(email_result, dict) else email_result
            tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""

            # Log in Salesforce (using account ID)
            log_salesforce_activity(account_id, email_content)

            # Collect Results
            results.append({
                "contact": contact_name,
                "account": account_name,
                "email_status": email_status + tracking_info,
                "subject": subject_line,
                "email_body": email_content,
                "tracking_id": email_result.get('tracking_id') if isinstance(email_result, dict) else None,
                "tracking_url": email_result.get('tracking_url') if isinstance(email_result, dict) else None
            })
            
        except Exception as e:
            print(f"❌ Error processing contact {contact.get('Name', 'Unknown')}: {e}")
            results.append({
                "contact": contact.get('Name', 'Unknown'),
                "account": contact.get('Account', {}).get('Name', 'Unknown'),
                "email_status": f"❌ Error: {str(e)}",
                "subject": "N/A",
                "email_body": "N/A",
                "tracking_id": None,
                "tracking_url": None
            })
    
    print(f"📊 Email sending completed. Results: {len(results)}")
    return jsonify({
        "message": f"Processed {len(results)} contacts (limited to {max_emails} to prevent spam)",
        "results": results
    })



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
            print(f"📧 Found original Message-ID: {message_id}")
            return message_id
        else:
            print(f"⚠️ No Message-ID found in original email, using Gmail ID: {gmail_message_id}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting original Message-ID: {e}")
        return None

def send_threaded_email_reply(to_email, subject, reply_content, original_message_id, sender_name):
    """
    Send a threaded email reply that maintains the conversation thread.
    Uses the same tracking system as send_new_email for consistent open rate tracking.
    """
    try:
        from email_tracker import EmailTracker
        import time
        import random
        
        # Initialize email tracker (same as send_new_email)
        tracker = EmailTracker()
        
        # Track the email and get tracking ID (same as send_new_email)
        tracking_id = tracker.track_email_sent(
            recipient_email=to_email,
            sender_email=EMAIL_USERNAME,
            subject=subject,
            campaign_name="AI Email Reply"
        )
        
        # Add tracking pixel to email content (same as send_new_email)
        tracked_email_content = tracker.add_tracking_to_email(reply_content, tracking_id, "https://web-production-6dfbd.up.railway.app")
        
        # Get the actual Message-ID from the original email for proper threading
        original_message_id_header = get_original_message_id(original_message_id)
        
        # Create email message with enhanced headers (same as send_new_email)
        msg = MIMEMultipart()
        msg["From"] = f"Jake Morgan - Affirm <{EMAIL_USERNAME}>"
        msg["To"] = to_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith('Re:') else subject
        msg["Reply-To"] = EMAIL_USERNAME
        msg["Return-Path"] = EMAIL_USERNAME
        msg["Message-ID"] = f"<{tracking_id}@affirm.com>"
        msg["X-Mailer"] = "Affirm Business Development"
        msg["X-Priority"] = "3"
        msg["X-MSMail-Priority"] = "Normal"
        msg["Importance"] = "Normal"
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@affirm.com?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["X-Affirm-Campaign"] = "AI Email Reply"
        msg["X-Affirm-Source"] = "Business Development"
        
        # Add proper threading headers using the actual Message-ID
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
        
        # Add random delay (same as send_new_email)
        delay = random.uniform(2, 5)
        print(f"⏱️ Waiting {delay:.1f} seconds before sending...")
        time.sleep(delay)
        
        # Send email via SMTP (same as send_new_email)
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.ehlo()
            server.sendmail(EMAIL_USERNAME, to_email, msg.as_string())
        
        print(f"✅ Tracked threaded email sent to {to_email}")
        return {
            'status': '✅ Email sent successfully',
            'tracking_id': tracking_id,
            'tracking_url': f"https://web-production-6dfbd.up.railway.app/tracking/details/{tracking_id}"
        }
        
    except Exception as e:
        print(f"❌ Error sending threaded email: {e}")
        return {'status': f'❌ Error: {str(e)}'}

def mark_emails_as_read(email_ids):
    """
    Mark emails as read in Gmail.
    """
    try:
        creds = authenticate_gmail()
        service = build('gmail', 'v1', credentials=creds)
        
        # Mark emails as read by removing the UNREAD label
        service.users().messages().batchModify(
            userId='me',
            body={'ids': email_ids, 'removeLabelIds': ['UNREAD']}
        ).execute()
        
        print(f"✅ Marked {len(email_ids)} emails as read")
        
    except Exception as e:
        print(f"❌ Error marking emails as read: {e}")
        raise e

# 🔹 New function for Workato - No Salesforce Dependencies
def reply_to_emails_with_accounts(accounts):
    """
    Process email replies using accounts provided by Workato instead of querying Salesforce.
    
    Args:
        accounts: List of account dictionaries with email, name, account_id, contact_id
    
    Returns:
        Dictionary with processing results
    """
    try:
        # Get emails needing replies using the provided accounts
        emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
        responses = []

        print(f"🔍 Processing {len(emails_needing_replies)} threads individually...")
        
        # Process each thread individually
        for i, email in enumerate(emails_needing_replies):
            thread_id = email.get('threadId', 'No ID')
            print(f"📧 Processing thread {i+1}/{len(emails_needing_replies)}: {thread_id}")
            
            # Extract contact information
            contact_name = email.get('contact_name', email['sender'].split("@")[0].capitalize())
            contact_email = email['sender']
            account_id = email.get('account_id')
            contact_id = email.get('contact_id')
            
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
                    subject=f"Re: {email['subject']}",
                    reply_content=ai_response,
                    original_message_id=email.get('message_id'),
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
                    'contact_id': contact_id,
                    'ai_reply_content': ai_response,
                    'original_email_body': email['body'],
                    'conversation_context': conversation_content
                }
                
                responses.append(response_info)
                print(f"✅ Reply sent successfully to {contact_name} ({contact_email})")
                
            except Exception as e:
                print(f"❌ Error processing email for {contact_name}: {e}")
                response_info = {
                    'thread_id': thread_id,
                    'contact_name': contact_name,
                    'contact_email': contact_email,
                    'subject': email['subject'],
                    'status': 'error',
                    'error': str(e),
                    'account_id': account_id,
                    'contact_id': contact_id,
                    'ai_reply_content': None,
                    'original_email_body': email['body'],
                    'conversation_context': conversation_content
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
        print(f"❌ Error in reply_to_emails_with_accounts: {e}")
        import traceback
        traceback.print_exc()
        raise e

def get_emails_needing_replies_with_accounts(accounts):
    """
    Get emails needing replies using accounts provided by Workato instead of Salesforce query.
    
    Args:
        accounts: List of account dictionaries with email, name, account_id, contact_id
    
    Returns:
        List of emails that need replies
    """
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    print("✅ Connected to Gmail API")

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

    print(f"📌 Processing {len(account_emails)} email addresses from Workato")

    # Fetch ALL emails from inbox (not just unread)
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=100).execute()
    messages = results.get('messages', [])
    if not messages:
        print("⚠️ No emails found in inbox!")
        return []

    print(f"📬 Found {len(messages)} total emails in inbox")

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
            print(f"📧 Found email from Workato account: {sender} - {subject}")

    print(f"📊 Found {len(emails)} emails from Workato-provided accounts")

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
            print(f"📧 Conversation thread {thread_id} from {latest_email['sender']} needs a reply")
        else:
            print(f"✅ Conversation thread {thread_id} from {latest_email['sender']} already has a reply")

    print(f"📬 Found {len(emails_needing_replies)} conversation threads needing replies")
    return emails_needing_replies

@app.route('/reply_to_emails', methods=['GET'])
def reply_to_emails():
    emails_needing_replies = get_emails_needing_replies()
    responses = []

    print(f"🔍 Processing {len(emails_needing_replies)} threads individually...")
    
    # Process each thread individually (don't group by sender)
    for i, email in enumerate(emails_needing_replies):
        thread_id = email.get('threadId', 'No ID')
        print(f"📧 Processing thread {i+1}/{len(emails_needing_replies)}: {thread_id}")
        
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
            
            # Log in Salesforce (using account_id like send_new_email)
            if account_id:
                log_salesforce_activity(account_id, ai_response)
            
            print(f"✅ Sent reply to thread {thread_id}")
            
        except Exception as e:
            print(f"❌ Error processing email from {contact_email}: {e}")
            email_status = "❌ Failed to process email"
            email_result = None
            tracking_info = ""
            ai_response = "<p>Sorry, I couldn't generate a response at this time.</p>"

        # Mark email as read
        try:
            mark_emails_as_read([email['id']])
        except Exception as e:
            print(f"❌ Error marking email as read: {e}")

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

    print(f"📊 Processed {len(responses)} conversation threads")
    return jsonify({
        "message": f"Processed {len(responses)} conversation threads",
        "responses": responses
    })

if __name__ == '__main__':
    app.run(debug=True)




# 🔹 Workato Endpoint for Reply to Emails (No Salesforce Dependencies)
@app.route('/api/workato/reply-to-emails', methods=['POST'])
def workato_reply_to_emails():
    """
    Workato endpoint to process email replies - SIMPLIFIED VERSION.
    
    Expected input format (much simpler):
    {
        "emails": ["contact@example.com", "another@example.com"]
    }
    
    OR even simpler:
    {
        "email": "contact@example.com"
    }
    """
    try:
        data = request.get_json() if request.is_json else {}
        
        # Handle both simple formats
        emails = []
        if 'email' in data:
            # Single email format
            emails = [data['email']]
        elif 'emails' in data:
            # Multiple emails format
            emails = data['emails']
        elif 'accounts' in data:
            # Legacy format - extract emails from accounts
            accounts = data['accounts']
            emails = [account.get('email') for account in accounts if account.get('email')]
        else:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter. Send either "email", "emails", or "accounts"',
                'timestamp': datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        if not emails or len(emails) == 0:
            return jsonify({
                'status': 'error', 
                'message': 'No valid email addresses provided',
                'timestamp': datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        print(f"📧 Workato triggered reply_to_emails at {datetime.now().isoformat()}")
        print(f"📊 Processing {len(emails)} email addresses from Workato")
        
        # Convert emails to simple account format for the function
        accounts = [{'email': email, 'name': email.split('@')[0].capitalize()} for email in emails]
        
        # Call the new function with Workato-provided accounts
        result = reply_to_emails_with_accounts(accounts)
        
        return jsonify({
            'status': 'success',
            'message': 'Reply to emails completed successfully',
            'timestamp': datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_processed': result.get('emails_processed', 0),
            'replies_sent': result.get('replies_sent', 0),
            'results': result
        })
        
    except Exception as e:
        print(f"❌ Workato reply_to_emails error: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error processing replies: {str(e)}',
            'timestamp': datetime.now().isoformat(),
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
                'timestamp': datetime.now().isoformat(),
                'emails_needing_replies': 0
            }), 400
        
        accounts = data['accounts']
        if not isinstance(accounts, list):
            return jsonify({
                'status': 'error', 
                'message': 'Accounts must be an array',
                'timestamp': datetime.now().isoformat(),
                'emails_needing_replies': 0
            }), 400
        
        # Get emails needing replies using Workato-provided accounts
        emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
        
        return jsonify({
            'status': 'success',
            'message': f'Found {len(emails_needing_replies)} emails needing replies',
            'timestamp': datetime.now().isoformat(),
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
        print(f"❌ Workato reply status error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error getting reply status: {str(e)}',
            'timestamp': datetime.now().isoformat(),
            'emails_needing_replies': 0
        }), 500

@app.route('/api/workato/send-new-emails', methods=['POST'])
def workato_send_new_emails():
    """Workato endpoint to trigger send_new_email function."""
    try:
        # Optional: Accept parameters from Workato
        data = request.get_json() if request.is_json else {}
        
        # Log the request
        print(f"📧 Workato triggered send_new_emails at {datetime.now().isoformat()}")
        
        # Call the existing send_new_email function
        result = send_new_email()
        
        # Extract data from the result
        if hasattr(result, 'get_json'):
            response_data = result.get_json()
        else:
            response_data = result
        
        # Return Workato-friendly response
        return jsonify({
            'status': 'success',
            'message': 'Send new emails completed successfully',
            'timestamp': datetime.now().isoformat(),
            'results': response_data,
            'emails_sent': len(response_data.get('responses', [])) if isinstance(response_data, dict) else 0
        })
        
    except Exception as e:
        print(f"❌ Workato send_new_emails error: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error sending new emails: {str(e)}',
            'timestamp': datetime.now().isoformat(),
            'emails_sent': 0
        }), 500

@app.route('/api/workato/workato-reply-to-emails', methods=['POST'])
def workato_reply_to_emails_new():
    """
    New Workato endpoint that replicates reply_to_emails functionality.
    Accepts Salesforce account data from Workato and processes email replies.
    
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
    
    Returns:
    {
        "status": "success/error",
        "message": "Processing summary",
        "timestamp": "2024-01-01T00:00:00",
        "accounts_processed": 5,
        "emails_processed": 3,
        "replies_sent": 2,
        "responses": [
            {
                "sender": "contact@example.com",
                "contact_name": "Contact Name",
                "account_id": "SF_Account_ID",
                "salesforce_id": "SF_Contact_ID",
                "thread_id": "thread_123",
                "subject": "Re: Your Message",
                "original_message": "Email content...",
                "ai_response": "AI generated response...",
                "email_status": "✅ Reply sent successfully",
                "tracking_id": "uuid-123",
                "tracking_url": "https://app.up.railway.app/tracking/details/uuid-123",
                "emails_processed": 1
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
                'timestamp': datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        accounts = data['accounts']
        if not isinstance(accounts, list) or len(accounts) == 0:
            return jsonify({
                'status': 'error', 
                'message': 'Accounts must be a non-empty array',
                'timestamp': datetime.now().isoformat(),
                'emails_processed': 0
            }), 400
        
        print(f"📧 Workato triggered workato-reply-to-emails at {datetime.now().isoformat()}")
        print(f"📊 Processing {len(accounts)} accounts from Workato")
        
        # Get emails needing replies using the provided accounts
        emails_needing_replies = get_emails_needing_replies_with_accounts(accounts)
        responses = []

        print(f"🔍 Processing {len(emails_needing_replies)} threads individually...")
        
        # Process each thread individually (replicating reply_to_emails logic)
        for i, email in enumerate(emails_needing_replies):
            thread_id = email.get('threadId', 'No ID')
            print(f"📧 Processing thread {i+1}/{len(emails_needing_replies)}: {thread_id}")
            
            # Extract contact information
            contact_name = email.get('contact_name', email['sender'].split("@")[0].capitalize())
            contact_email = email['sender']
            account_id = email.get('account_id')
            salesforce_id = email.get('contact_id')
            
            # Sender information (matching reply_to_emails)
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
                
                # Log in Salesforce (using account_id like reply_to_emails)
                if account_id:
                    log_salesforce_activity(account_id, ai_response)
                
                print(f"✅ Sent reply to thread {thread_id}")
                
            except Exception as e:
                print(f"❌ Error processing email from {contact_email}: {e}")
                email_status = "❌ Failed to process email"
                email_result = None
                tracking_info = ""
                ai_response = "<p>Sorry, I couldn't generate a response at this time.</p>"

            # Mark email as read
            try:
                mark_emails_as_read([email['id']])
            except Exception as e:
                print(f"❌ Error marking email as read: {e}")

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

        print(f"📊 Processed {len(responses)} conversation threads")
        
        # Calculate success metrics
        successful_replies = len([r for r in responses if '✅' in r.get('email_status', '')])
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(responses)} conversation threads',
            'timestamp': datetime.now().isoformat(),
            'accounts_processed': len(accounts),
            'emails_processed': len(emails_needing_replies),
            'replies_sent': successful_replies,
            'responses': responses
        })
        
    except Exception as e:
        print(f"❌ Workato workato-reply-to-emails error: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error processing replies: {str(e)}',
            'timestamp': datetime.now().isoformat(),
            'emails_processed': 0
        }), 500


# 🔹 Google Sheets Daily Data Export
def get_google_sheets_credentials():
    """Get Google Sheets API credentials from environment variables."""
    try:
        credentials_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
        if not credentials_json:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS_JSON environment variable not set")
        
        import json
        creds_info = json.loads(credentials_json)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return creds
    except Exception as e:
        print(f"❌ Error getting Google Sheets credentials: {e}")
        return None

def export_email_data_to_sheets():
    """Export email tracking data to Google Sheets."""
    try:
        # TODO: Database connection not available in this version
        # conn = get_db_connection()
        # if not conn:
        print("❌ Database connection not available in this version")
        return False
        
        cursor = conn.cursor()
        
        # Query email tracking data
        query = """
        SELECT 
            et.tracking_id,
            et.recipient_email,
            et.sender_email,
            et.subject,
            et.campaign_name,
            et.sent_at,
            et.open_count,
            et.last_opened_at,
            et.created_at,
            COUNT(eo.id) as total_opens,
            MAX(eo.opened_at) as first_opened_at
        FROM email_tracking et
        LEFT JOIN email_opens eo ON et.tracking_id = eo.tracking_id
        GROUP BY et.tracking_id, et.recipient_email, et.sender_email, et.subject, 
                 et.campaign_name, et.sent_at, et.open_count, et.last_opened_at, et.created_at
        ORDER BY et.sent_at DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("📊 No email data found for the last 30 days")
            return True
        
        # Convert to DataFrame
        columns = [
            'tracking_id', 'recipient_email', 'sender_email', 'subject', 
            'campaign_name', 'sent_at', 'open_count', 'last_opened_at', 
            'created_at', 'total_opens', 'first_opened_at'
        ]
        df = pd.DataFrame(rows, columns=columns)
        
        # Get Google Sheets credentials
        creds = get_google_sheets_credentials()
        if not creds:
            return False
        
        # Connect to Google Sheets
        gc = gspread.authorize(creds)
        
        # Get the spreadsheet
        spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID')
        if not spreadsheet_id:
            print("❌ GOOGLE_SHEETS_ID environment variable not set")
            return False
        
        try:
            spreadsheet = gc.open_by_key(spreadsheet_id)
        except:
            print("❌ Could not access Google Sheet. Check GOOGLE_SHEETS_ID")
            return False
        
        # Get or create worksheet for today
        today = datetime.now().strftime('%Y-%m-%d')
        worksheet_name = f"Email Data {today}"
        
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            worksheet.clear()
        except:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
        
        # Prepare data
        headers = [
            'Tracking ID', 'Recipient Email', 'Sender Email', 'Subject', 
            'Campaign Name', 'Sent At', 'Open Count', 'Last Opened At', 
            'Created At', 'Total Opens', 'First Opened At', 'Open Rate %'
        ]
        
        df['open_rate'] = (df['total_opens'] / 1 * 100).round(2)
        
        data_rows = [headers]
        for _, row in df.iterrows():
            data_row = [
                str(row['tracking_id']),
                str(row['recipient_email']),
                str(row['sender_email']),
                str(row['subject']),
                str(row['campaign_name']),
                row['sent_at'].strftime('%Y-%m-%d %H:%M:%S') if row['sent_at'] else '',
                int(row['open_count']),
                row['last_opened_at'].strftime('%Y-%m-%d %H:%M:%S') if row['last_opened_at'] else '',
                row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else '',
                int(row['total_opens']),
                row['first_opened_at'].strftime('%Y-%m-%d %H:%M:%S') if row['first_opened_at'] else '',
                f"{row['open_rate']:.2f}%"
            ]
            data_rows.append(data_row)
        
        # Update worksheet
        worksheet.update('A1', data_rows)
        
        # Add summary
        summary_row = len(data_rows) + 2
        summary_data = [
            ['SUMMARY STATISTICS'],
            ['Total Emails Sent', len(df)],
            ['Total Opens', int(df['total_opens'].sum())],
            ['Average Open Rate', f"{(df['total_opens'].sum() / len(df) * 100):.2f}%"],
            ['Export Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]
        
        worksheet.update(f'A{summary_row}', summary_data)
        
        conn.close()
        
        print(f"✅ Successfully exported {len(df)} email records to Google Sheets")
        print(f"📊 Worksheet: {worksheet_name}")
        print(f"📈 Total opens: {int(df['total_opens'].sum())}")
        print(f"📊 Average open rate: {(df['total_opens'].sum() / len(df) * 100):.2f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Error exporting to Google Sheets: {e}")
        import traceback
        traceback.print_exc()
        return False

@app.route('/api/export-to-sheets', methods=['POST'])
def export_to_sheets():
    """Export email tracking data to Google Sheets."""
    try:
        success = export_email_data_to_sheets()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Email data successfully exported to Google Sheets',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to export data to Google Sheets'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/schedule-daily-export', methods=['POST'])
def schedule_daily_export():
    """Schedule daily export to Google Sheets (for cron jobs)."""
    try:
        success = export_email_data_to_sheets()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Daily export completed successfully',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Daily export failed'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Daily export error: {str(e)}'
        }), 500

# Railway deployment configuration
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
