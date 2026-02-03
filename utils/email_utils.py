"""
Email utility functions

Helper functions for email formatting, parsing, and normalization.
"""

import re
from config import PARDOT_EMAIL_TEMPLATE


def format_pardot_email(first_name, email_content, recipient_email, sender_name):
    """
    Inserts dynamic data into the Pardot email template.
    Ensures email content is formatted correctly with line breaks.
    """
    formatted_email = email_content.replace("\n", "<br>")

    return PARDOT_EMAIL_TEMPLATE.replace("{{FIRST_NAME}}", first_name) \
                                .replace("{{EMAIL_CONTENT}}", formatted_email) \
                                .replace("{{SENDER_NAME}}", sender_name) \
                                .replace("{{RECIPIENT_EMAIL}}", recipient_email) \
                                .replace("{{UNSUBSCRIBE_LINK}}", "https://www.affirm.com/unsubscribe")


def normalize_email(email):
    """
    Remove Gmail aliases (+ addressing) for normalization.
    Example: john+test@gmail.com -> john@gmail.com
    """
    if '+' in email and '@gmail.com' in email.lower():
        local, domain = email.split('@')
        local = local.split('+')[0]
        return f"{local}@{domain}"
    return email


def strip_html_tags(html_text):
    """
    Remove HTML tags from text.
    Returns plain text version.
    """
    if not html_text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html_text)


def remove_quoted_text(text):
    """
    Remove quoted/replied text from emails.
    Looks for common reply patterns.
    """
    if not text:
        return text

    # Common reply patterns
    patterns = [
        r'On .* wrote:',
        r'From:.*\n.*\n.*\n',
        r'-----Original Message-----',
        r'________________________________',
        r'> .*'  # Quoted lines
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.DOTALL)

    return text.strip()
