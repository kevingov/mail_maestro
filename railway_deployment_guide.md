# 🚂 Railway Deployment Guide

## Step 1: Create Railway Account

1. Go to [railway.app](https://railway.app)
2. Click "Sign Up" 
3. Choose "Sign up with GitHub" (recommended)
4. Authorize Railway to access your GitHub account

## Step 2: Deploy Your Tracking Pixel

### Option A: Deploy from GitHub (Recommended)

1. **Push your code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Add email tracking pixel for Railway deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/mail_hackathon.git
   git push -u origin main
   ```

2. **Connect to Railway:**
   - Go to [railway.app/dashboard](https://railway.app/dashboard)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your `mail_hackathon` repository
   - Railway will automatically detect it's a Python app

3. **Configure the deployment:**
   - Railway will automatically use `railway_app.py` as the entry point
   - The app will be available at a URL like: `https://your-app-name.railway.app`

### Option B: Deploy with Railway CLI

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login and deploy:**
   ```bash
   railway login
   railway init
   railway up
   ```

## Step 3: Get Your Public URL

After deployment, Railway will give you a URL like:
- `https://your-app-name.railway.app`

This is your new tracking pixel base URL!

## Step 4: Update Your Email Functions

Once you have your Railway URL, update your email sending functions:

```python
# Replace this in your 2025_hackathon.py
base_url="https://your-app-name.railway.app"
```

## Step 5: Test Your Deployment

1. Visit your Railway URL to see the home page
2. Go to `/test` to create a test tracking ID
3. Click the tracking URL to test the pixel
4. Check `/api/health` to verify everything is working

## 🎯 Benefits of Railway Deployment

✅ **Always Online**: Your tracking pixel works 24/7
✅ **Global Access**: Works from any device, anywhere
✅ **Automatic HTTPS**: Secure connections
✅ **Free Tier**: Generous free usage limits
✅ **Easy Updates**: Just push to GitHub to update

## 📱 Testing on Your Phone

Once deployed, your tracking pixel will work on:
- ✅ Mobile email clients (Gmail, Outlook, etc.)
- ✅ Desktop email clients
- ✅ Any device with internet access
- ✅ Different WiFi networks
- ✅ Cellular data

## 🔧 Environment Variables (Optional)

You can set these in Railway dashboard:
- `SECRET_KEY`: For Flask sessions
- `DATABASE_URL`: For custom database location

## 🚨 Important Notes

1. **Database**: Railway will create a persistent SQLite database
2. **Logs**: Check Railway dashboard for deployment logs
3. **Monitoring**: Use `/api/health` endpoint for monitoring
4. **Updates**: Push changes to GitHub to automatically update

Your tracking pixel will now work globally! 🌍
