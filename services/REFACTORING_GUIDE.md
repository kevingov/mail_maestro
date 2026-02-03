# Services Refactoring Guide

This directory should contain business logic services extracted from railway_app.py.

## Recommended Service Modules

### gmail_service.py
Move from railway_app.py:
- `authenticate_gmail()` (lines ~274-349)
- `send_email()` (lines ~1147-1300)
- `send_threaded_email_reply()` (lines ~1300-1439)
- `reply_to_emails_with_accounts()` (lines ~1441-2120)
- `get_emails_needing_replies_with_accounts()` (lines ~2121-2645)
- `get_original_message_id()` (lines ~XXX)
- `has_been_replied_to()` (lines ~XXX - 27-hour logic)

### openai_service.py
Move from railway_app.py:
- `generate_ai_response()` (lines ~665-1000)
- `generate_ai_summary_of_message()` (lines ~1000-1100)
- `generate_message()` (lines ~1100-1145)

### salesforce_service.py
Move from railway_app.py:
- `is_salesforce_case_notification()` (lines ~625-663)
- `parse_activities()` (lines ~6587-6650)
- `normalize_activity()` (lines ~6650-6730)
- `check_if_email_already_sent()` (lines ~6730-7000)

### sheets_service.py
Move from railway_app.py:
- `get_google_sheets_credentials()` (lines ~7443-7500)
- `write_to_google_sheets()` (lines ~7500-7600)
- `log_dump_to_automation_logs()` (lines ~7600-7650)

### prompt_service.py
Move from railway_app.py:
- `create_versioned_endpoint()` (lines ~5050-5080)
- `get_versioned_prompt_from_db()` (lines ~5080-5100)
- `load_prompt_versions()` (lines ~5100-5121)

## Refactoring Steps

1. Create each service module file
2. Copy relevant functions from railway_app.py
3. Update imports to use config module
4. Update function calls in railway_app.py to import from services
5. Test each service independently
6. Gradually migrate routes to use new services

## Dependencies

Each service should:
- Import from `config` for configuration
- Import from `models.database` for database operations
- Import from `utils` for utility functions
- Be independently testable with mocked dependencies
