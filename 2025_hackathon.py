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

# 🔹 Fetch salesforce accounts so we can match the emails
def fetch_salesforce_accounts():
    """
    Fetch all account email addresses from Salesforce.
    """
    try:
        query = "SELECT Id, Name, Email__c FROM Account WHERE Email__c != NULL"
        accounts = sf.query(query)['records']
        
        # ✅ Ensure the function returns a dictionary
        account_emails = {acc['Email__c'].strip().lower(): acc['Id'] for acc in accounts if 'Email__c' in acc}

        print("📌 Salesforce Accounts Fetched:", account_emails)  # ✅ Debugging
        return account_emails
    except Exception as e:
        print(f"❌ Error fetching Salesforce accounts: {e}")
        return {}  # ✅ Return empty dictionary instead of None

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
def get_unread_emails():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    print("✅ Connected to Gmail API")

    # # Get Salesforce account emails
    salesforce_accounts = fetch_salesforce_accounts()
    print("📌 Fetched Salesforce accounts:", salesforce_accounts)  # Debugging

    # Fetch only the top 5 unread emails
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=50).execute()
    messages = results.get('messages', [])
    if not messages:
        print("⚠️ No unread emails found!")
        return []

    emails = []
    for msg in messages:
        msg_id = msg['id']
        email_data = service.users().messages().get(userId='me', id=msg_id).execute()
        msg_payload = email_data['payload']
        headers = msg_payload['headers']

        sender = next(h['value'] for h in headers if h['name'] == 'From')
        sender = extract_email(sender)  # ✅ Extracts only the email part
        subject = next(h['value'] for h in headers if h['name'] == 'Subject')

        # Decode the email body
        body = extract_email_body(msg_payload)

        # emails.append({'id': msg_id, 'sender': sender, 'subject': subject, 'body': body})
        # ✅ Only add the email if the sender exists in Salesforce
        if sender in salesforce_accounts:
            emails.append({
                'id': msg_id,
                'sender': sender,
                'subject': subject,
                'body': body,
                'salesforce_id': salesforce_accounts[sender]  # Add SF Account ID
            })
        else:
            print(f"⚠️ Email from {sender} does not match any Salesforce account")  # Debugging
    print("✅ Processed Emails:", emails)  # ✅ Debugging
    return emails

# 🔹 Use AI to Generate Smart Responses
def generate_ai_response(email_body, sender_name, recipient_name):
    """
    Generates an AI response strictly aligned with Affirm's branding guidelines.
    """

    prompt = f"""
    {AFFIRM_VOICE_GUIDELINES}

    You are an AI-powered business development assistant.
    You received this email from a {recipient_name}:

    {email_body}

    Generate a **short, personalized response email**.

    If it's a meeting request, provide a scheduling link.
    If it's a general inquiry, respond with relevant information.
    If it's a rejection, acknowledge and thank them.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": AFFIRM_VOICE_GUIDELINES},
                      {"role": "user", "content": prompt}]
        )

        if response and response.choices:
            response_text = response.choices[0].message.content.strip()  # ✅ Ensure response is captured
        else:
            response_text = "Sorry, I couldn't generate a response at this time."  # ✅ Fallback if empty response
        
    except Exception as e:
        print(f"❌ Error generating AI response: {e}")
        response_text = "Sorry, there was an error generating the response."
        
    response.choices[0].message.content.strip()
    return format_pardot_email(first_name=recipient_name, 
                               email_content=response_text, 
                               recipient_email="recipient@email.com", 
                               sender_name=sender_name)

# 🔹 Send AI-Generated Email Replies with Tracking
def send_email_reply(to_email, subject, html_body, campaign_name="AI Reply", base_url="http://172.24.37.98:5001"):
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
    # """
    # Log an email reply in Salesforce, attaching it to the relevant account.
    # """
    sf.Task.create({
        'Subject': f"Email Reply from {email['sender']}",
        'Description': f"Subject: {email['subject']}\n\nMessage: {email['body']}",
        'Status': 'Completed',
        'Priority': 'Normal',
        'WhatId': email['salesforce_id']  # Attach to Salesforce Account
    })

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
        
def generate_message(merchant_name, last_activity, merchant_industry, merchant_website, sender_name):
    """
    Creates an Affirm-branded outreach email using AI while following Affirm's guidelines.
    """
    prompt = f"""
    {AFFIRM_VOICE_GUIDELINES}
    
    Generate a **short, personalized marketing email** explaining why {merchant_name} in the {merchant_industry} industry should integrate Affirm. Use {merchant_name} and {merchant_industry} to personalize.

    - **Subject Line:** Must be compelling and aligned with Affirm's branding.
    - **Email Body:** 
        - Greet the recipient professionally and personably.
        - Explain the benefits of Affirm's BNPL model in 3 sentences.
        - Close with a strong **call to action**: "Let's connect! Call us at +1-555-1234 or reply to this email."

    **Context:**
    - Business Name: {merchant_name}
    - Last Activity: {last_activity}
    - Industry: {merchant_industry}
    - Website: {merchant_website}

    **Output Format:**
    - **Subject Line:** [Generated Subject Here]
    - **Email Body:** [Generated Email Content Here]

  
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": AFFIRM_VOICE_GUIDELINES},
                      {"role": "user", "content": prompt}]
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

# 🔹 Function: Send Email via SMTP with Tracking
def send_email(to_email, merchant_name, subject_line, email_content, campaign_name=None, base_url="http://172.24.37.98:5001"):
    try:
        from email_tracker import EmailTracker
        
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
        
        # Create email message
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USERNAME
        msg["To"] = to_email
        msg["Subject"] = subject_line

        msg.attach(MIMEText(tracked_email_content, "html"))
        print(f"📧 Email with tracking pixel prepared for {to_email}")
        print(f"🔍 Tracking ID: {tracking_id}")

        # Send email via SMTP
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()  # Secure connection
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USERNAME, to_email, msg.as_string())

        print(f"✅ Tracked email sent to {to_email}")
        return {
            'status': f"✅ Email sent to {to_email} with subject: {subject_line}",
            'tracking_id': tracking_id,
            'tracking_url': f"{base_url}/tracking/details/{tracking_id}"
        }

    except Exception as e:
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
            body { font-family: Helvetica, Arial, sans-serif; background-color: #f4f4f4; padding: 20px; margin: 0; }
            .container { max-width: 600px; background: white; padding: 20px; margin: auto;
                        border-radius: 10px; box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1); }
            h2 { color: #333; text-align: center; }
            .footer { font-size: 12px; text-align: center; color: gray; margin-top: 20px; }
            .logo-container { text-align: center; padding: 20px; }
            .logo-container img { width: 150px; display: block; margin: auto; max-width: 100%; }
        </style>
    </head>
    <body>

        <!-- 🔹 Email Wrapper -->
        <div class="container">

            <!-- 🔹 Affirm Logo (Header) -->
            <div class="logo-container">
                <img src="https://info.affirm.com/l/778433/2022-11-09/2mwml97/778433/1668036159Ur3IjmTf/Logo_affirm_for_business_full_logo_stacked.png" 
                    alt="Affirm Logo">
            </div>
            <!-- 🔹 Greeting -->
            <h2>Hello {{FIRST_NAME}},</h2>

            <!-- 🔹 Email Content -->
            <p style="line-height: 1.6; font-size: 16px;">{{EMAIL_CONTENT}}</p>

            <!-- 🔹 Closing -->
            <p>Best regards,</p>
            <p><strong>{{SENDER_NAME}}</strong></p>
        
        </div>

        <!-- 🔹 Footer Section -->
        <div class="footer">
            <p>This email was sent to: {{RECIPIENT_EMAIL}}</p>
            <p>
                <a href="{{UNSUBSCRIBE_LINK}}" rel="nofollow,noreferrer">Unsubscribe</a> |
                <a href="https://www.affirm.com/privacy" rel="nofollow,noreferrer">Privacy Policy</a> |
                <a href="https://businesshub.affirm.com/hc/en-us" rel="nofollow,noreferrer">Business Resource Center</a>
            </p>
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

user_info = sf.query("SELECT Id, Name, Email FROM User LIMIT 1")
print(user_info)




@app.route('/send_new_email')
def send_new_email():
    merchants = fetch_merchants()
    results = []

    
    for index, merchant in merchants.iterrows():  # Correct way to iterate
        merchant_name = merchant["Name"]  # Now it correctly accesses a column
        merchant_email = merchant["Email__c"]
        last_activity = merchant["LastActivityDate"]
        merchant_website = merchant["Website"]
        merchant_industry = merchant["Industry"]
        sender_name = "Affirm Team"

        if not merchant_email:
            continue  # Skip if no email

        # ✅ Generate Subject Line & Email Content with AI
        subject_line, email_content = generate_message(merchant_name, last_activity, merchant_industry, merchant_website, sender_name)

         # ✅ Ensure HTML email format
        formatted_email = format_pardot_email(first_name=merchant_name,
                                              email_content=email_content,
                                              recipient_email=merchant_email,
                                              sender_name=sender_name)

        # ✅ Send HTML Email with Tracking
        email_result = send_email(merchant_email, merchant_name, subject_line, formatted_email, campaign_name="New Merchant Outreach")
        email_status = email_result['status'] if isinstance(email_result, dict) else email_result
        tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""


        # Log in Salesforce
        log_salesforce_activity(merchant["Id"], email_content)

        # Collect Results
        results.append({
            "merchant": merchant_name,
            "email_status": email_status + tracking_info,
            "subject": subject_line,
            "email_body": email_content,
            "tracking_id": email_result.get('tracking_id') if isinstance(email_result, dict) else None,
            "tracking_url": email_result.get('tracking_url') if isinstance(email_result, dict) else None
        })
    print(results)
    print(merchants)
    return jsonify(results)



@app.route('/reply_to_emails', methods=['GET'])
def reply_to_emails():
    unread_emails = get_unread_emails()
    responses = []

    for email in unread_emails:
        recipient_name = email['sender'].split("@")[0].capitalize()  # Extract first name from email
        sender_name = "Your Company Team"  # Change to your actual sender
        
        try:
            ai_response = generate_ai_response(email['body'], sender_name, recipient_name)  # ✅ Ensure AI response is captured
        except Exception as e:
            print(f"❌ Error generating AI response: {e}")
            ai_response = "<p>Sorry, I couldn't generate a response at this time.</p>"  # ✅ Fallback if AI fails
        log_salesforce_reply(email)  # Log email in Salesforce


        try:
            email_result = send_email_reply(email['sender'], email['subject'], ai_response, campaign_name="AI Email Replies")  # ✅ Ensure it sends a valid response
            email_status = email_result['status'] if isinstance(email_result, dict) else email_result
            tracking_info = f" | Tracking ID: {email_result.get('tracking_id', 'N/A')}" if isinstance(email_result, dict) else ""
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            email_status = "❌ Failed to send email"
            email_result = None
            tracking_info = ""

        responses.append({
            "sender": email['sender'],
            "subject": email['subject'],
            "original_message": email['body'],
            "ai_response": ai_response,
            "email_status": email_status + tracking_info,
            "tracking_id": email_result.get('tracking_id') if isinstance(email_result, dict) else None,
            "tracking_url": email_result.get('tracking_url') if isinstance(email_result, dict) else None
        })
    
    return jsonify(responses)  # ✅ Convert list to JSON             

@app.route('/sfdc_accounts_html', methods=['GET'])
def get_sfdc_accounts_html():
    """
    API endpoint to return all Salesforce accounts in an HTML table.
    """
    accounts_dict = fetch_salesforce_accounts()

    if not accounts_dict:
        return "<h3>No accounts found in Salesforce.</h3>"

    df = pd.DataFrame(list(accounts_dict.items()), columns=['Email', 'Account ID'])

    return df.to_html(index=False)  # ✅ Convert DataFrame to HTML table

@app.route('/debug_emails', methods=['GET'])
def debug_emails():
    print("Fetching unread emails...")  # ✅ Log start of function
    unread_emails = get_unread_emails()
    
    print("Unread Emails:", unread_emails)  # ✅ Log result of API call
    
    if not unread_emails:
        return jsonify({"message": "No unread emails found"}), 200
    return jsonify(unread_emails)

@app.route('/debug_gmail', methods=['GET'])
def debug_gmail():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    # Try fetching emails without filters
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=5).execute()
    
    return jsonify(results)


if __name__ == '__main__':
    app.run(debug=True)
