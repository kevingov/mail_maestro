import os

class Config:
    # SECRET_KEY = os.environ.get('SECRET_KEY', 'a3f4d9c8b1e6f7d2a4c8e9b3f7c6d2e1a4b9e7c5d2a3f6b7c8d9e1f2a4c5b7e8') # random key
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///bookkeeping_agent.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OAUTHLIB_INSECURE_TRANSPORT = True  # Enable for local development
    QUICKBOOKS_CLIENT_ID = os.environ.get('QUICKBOOKS_CLIENT_ID', 'ABgtFRDaFWnI3zHHUYcgKMrQDHpVMHMSbJTFSai175NL4NCY2K')
    QUICKBOOKS_CLIENT_SECRET = os.environ.get('QUICKBOOKS_CLIENT_SECRET', '49IQK0Zgr124Gpa3wWDynO7TrAcCy15QQaO2A7kH')
    REDIRECT_URI = 'https://5fff-179-42-214-224.ngrok-free.app/authorize'