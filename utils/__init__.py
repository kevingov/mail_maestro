"""
Utility functions package
"""

from .email_utils import (
    format_pardot_email,
    normalize_email,
    strip_html_tags,
    remove_quoted_text,
    extract_email_body,
    remove_existing_signature
)

__all__ = [
    'format_pardot_email',
    'normalize_email',
    'strip_html_tags',
    'remove_quoted_text',
    'extract_email_body',
    'remove_existing_signature'
]
