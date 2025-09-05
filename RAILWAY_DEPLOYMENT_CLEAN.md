# 🚂 Clean Railway Deployment

## Files You Need for Railway

### ✅ Required Files:
1. `railway_app_minimal.py` - Main app (minimal version)
2. `email_tracker.py` - Email tracking logic
3. `requirements_minimal.txt` - Python dependencies
4. `Procfile` - Railway deployment config
5. `.gitignore` - Exclude sensitive files

### ❌ Files to Exclude:
- `2025_hackathon.py` - Contains secrets, keep local only
- `config.py` - Contains secrets, keep local only
- `flask_env/` - Virtual environment
- `yodavenv/` - Old virtual environment
- `*.db` - Database files
- `token.pickle` - Gmail tokens
- `credentials.json` - Gmail credentials
- `.env` - Environment variables

## 🚀 Deployment Steps

### 1. Clean Your Repository
```bash
# Remove sensitive files from Git
git rm --cached *.db
git rm --cached token.pickle
git rm --cached credentials.json
git rm --cached .env

# Add .gitignore
git add .gitignore
git commit -m "Add .gitignore and remove sensitive files"
```

### 2. Push to GitHub
```bash
git add .
git commit -m "Add Railway deployment files"
git push origin main
```

### 3. Deploy to Railway
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Railway will auto-detect Python and deploy

### 4. Get Your Public URL
Railway will give you a URL like: `https://your-app-name.railway.app`

### 5. Update Your Local Email Functions
```bash
python3 update_railway_url.py
# Enter your Railway URL when prompted
```

## 🔒 Security Features

- ✅ No secrets in code
- ✅ Environment variables for sensitive data
- ✅ Minimal attack surface
- ✅ Only essential endpoints
- ✅ Proper error handling

## 📱 What This Gives You

- ✅ **Global Tracking**: Works from any device, anywhere
- ✅ **Always Online**: 24/7 availability
- ✅ **Secure**: No exposed secrets
- ✅ **Scalable**: Railway handles scaling
- ✅ **HTTPS**: Automatic SSL certificates

Your tracking pixel will work on phones, tablets, and any device with internet access! 🌍
