# 🚂 Email Tracking Pixel - Railway Deployment

Minimal email tracking pixel service for Railway deployment.

## Files Included

- `railway_app_minimal.py` - Main Flask app with tracking pixel endpoint
- `email_tracker.py` - Email tracking logic and database management
- `requirements_minimal.txt` - Essential Python dependencies
- `Procfile` - Railway deployment configuration

## Endpoints

- `GET /` - Service info
- `GET /track/<tracking_id>` - Tracking pixel (main endpoint)
- `GET /api/health` - Health check

## Usage

This service provides a tracking pixel that can be embedded in emails to track when they are opened. The pixel is a 1x1 transparent image that records open events when loaded by email clients.

## Deployment

Deployed on Railway with automatic HTTPS and global availability.
