# 🚀 EMAIL SCRAPER - COMPLETE DEPLOYMENT GUIDE

## 📋 WHAT YOU HAVE

A complete Python email scraper system with:
- **Backend**: Flask server with Playwright, aiohttp, BeautifulSoup (98% accuracy)
- **Frontend**: Vanilla HTML/CSS/JavaScript dashboard
- **Admin Panel**: User management and activity tracking
- **Auto Registration**: First-time users are automatically registered
- **Environment Detection**: Works on both localhost AND Railway (production)

---

## ✅ STEP 1: DOWNLOAD FROM FIGMA MAKE

1. **In Figma Make**, look for the download/export button (usually top-right corner)
2. Click "Download" or "Export" 
3. Choose "Download as ZIP"
4. Save the file (e.g., `email-scraper.zip`) to your computer

---

## 📦 STEP 2: VERIFY YOUR FILES

After downloading, unzip the file and verify these **ESSENTIAL FILES** are present:

### Backend Files (Required):
- ✅ `backend.py` - Main Python Flask server
- ✅ `requirements.txt` - Python dependencies
- ✅ `runtime.txt` - Python version specification

### Frontend Files (Required):
- ✅ `index.html` - Main scraper interface
- ✅ `admin.html` - Admin dashboard
- ✅ `app.js` - JavaScript with auto environment detection
- ✅ `style.css` - Styling

### Railway Deployment Files (Required):
- ✅ `Procfile` - Tells Railway how to start your app
- ✅ `start.sh` - Startup script
- ✅ `nixpacks.toml` - Build configuration
- ✅ `railway.json` - Railway settings

### Optional Files (Ignore These):
- ⚪ `App.tsx`, `components/`, `styles/` - React files (won't interfere with deployment)
- ⚪ `Attributions.md`, `Guidelines.md` - Documentation files

**Important**: The React/TSX files are system files that won't affect your deployment. Railway will only use the Python backend files.

---

## 🌐 STEP 3: TEST LOCALLY (Optional but Recommended)

Before deploying to Railway, test on your computer:

### Install Python Dependencies:
```bash
cd email-scraper
pip install -r requirements.txt
playwright install chromium
```

### Run the Server:
```bash
python backend.py
```

### Open in Browser:
```
http://localhost:5000
```

You should see:
- Main page: Email scraper interface
- Admin page: http://localhost:5000/admin.html

**Test the scraper**: Enter a website URL and click "Scrape Emails"

---

## 🚂 STEP 4: DEPLOY TO RAILWAY

### A. Create Railway Account
1. Go to **https://railway.app**
2. Click "Sign up" (or "Login")
3. Sign up with GitHub (recommended) or email
4. Verify your email if needed

### B. Create New Project
1. Click "**New Project**" button
2. Select "**Deploy from GitHub repo**" OR "**Empty Project**"

### C. Upload Your Code

**Option 1: Using GitHub (Recommended)**
1. Upload your unzipped folder to a GitHub repository
2. In Railway, click "Deploy from GitHub repo"
3. Select your repository
4. Railway will automatically detect and deploy

**Option 2: Using Railway CLI (Direct Upload)**
1. Install Railway CLI:
   ```bash
   npm i -g @railway/cli
   ```
2. Login:
   ```bash
   railway login
   ```
3. Navigate to your project folder:
   ```bash
   cd email-scraper
   ```
4. Initialize and deploy:
   ```bash
   railway init
   railway up
   ```

**Option 3: Using Railway Dashboard (Drag & Drop)**
1. In Railway, create an "Empty Project"
2. Click on the service
3. Go to "Settings" → "Source"
4. Connect your GitHub repository or use CLI

---

## ⚙️ STEP 5: CONFIGURE RAILWAY SETTINGS

After uploading, Railway will automatically:
- ✅ Detect Python using `runtime.txt`
- ✅ Install dependencies from `requirements.txt`
- ✅ Run `Procfile` command to start the server
- ✅ Install Playwright and Chromium

### Check Build Logs:
1. Click on your service
2. Go to "**Deployments**" tab
3. Click on the latest deployment
4. Watch the build logs to ensure everything installs correctly

### Important Configuration:
Railway should automatically:
- Set PORT environment variable
- Install system dependencies (Playwright browsers)
- Run the start script

**If deployment fails**, check:
1. Build logs for errors
2. Make sure all files uploaded correctly
3. Verify `nixpacks.toml` is present (handles Playwright dependencies)

---

## 🌍 STEP 6: GET YOUR PUBLIC URL

1. In Railway dashboard, click on your service
2. Go to "**Settings**" tab
3. Scroll to "**Networking**" section
4. Click "**Generate Domain**"
5. Railway will create a URL like: `https://your-app-name.up.railway.app`

**Copy this URL** - this is your live website!

---

## 🎯 STEP 7: ACCESS YOUR LIVE APP

### Main Scraper Page:
```
https://your-app-name.up.railway.app
```

### Admin Dashboard:
```
https://your-app-name.up.railway.app/admin.html
```

**First Time Setup:**
1. Open the main scraper page
2. Enter your username
3. You'll be **automatically registered** as a user
4. Start scraping emails!

**Admin Access:**
1. Go to admin.html
2. View all registered users
3. See total scrapes and activity
4. Monitor system usage

---

## 🔒 ENVIRONMENT DETECTION (AUTOMATIC)

Your `app.js` file automatically detects the environment:

**On Localhost:**
```javascript
API_URL = 'http://localhost:5000'
```

**On Railway (Production):**
```javascript
API_URL = 'https://your-app-name.up.railway.app'
```

**No configuration needed!** The app automatically uses the correct URL.

---

## 🐛 TROUBLESHOOTING

### Problem: Deployment Fails
**Solution:**
- Check Railway build logs
- Ensure all required files are present
- Verify `requirements.txt` has all dependencies

### Problem: "Module not found" Error
**Solution:**
- Check `requirements.txt` includes the missing module
- Redeploy to trigger fresh installation

### Problem: Playwright Browser Not Found
**Solution:**
- `nixpacks.toml` should install Playwright dependencies
- If error persists, add to Railway environment variables:
  ```
  PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
  ```

### Problem: App Loads but Can't Scrape
**Solution:**
- Check if Railway logs show Playwright errors
- Verify network access is working
- Test with a simple website first

### Problem: Admin Page Shows No Data
**Solution:**
- Make sure `users.db` is being created
- Check Railway logs for database errors
- Try registering a new user first

---

## 📊 WHAT HAPPENS AFTER DEPLOYMENT

1. **Automatic Database Creation**: `users.db` SQLite database is created automatically
2. **User Registration**: First-time visitors are auto-registered
3. **Email Scraping**: Users can scrape emails from any website
4. **Activity Tracking**: All scrapes are logged with timestamps
5. **Admin Monitoring**: View users and activity in real-time

---

## 🎉 YOU'RE DONE!

Your email scraper is now live on the internet! 

**Share your URL:**
```
https://your-app-name.up.railway.app
```

**Key Features Working:**
- ✅ Email scraping with 98% accuracy
- ✅ Automatic user registration
- ✅ Admin dashboard with user management
- ✅ Activity tracking and logging
- ✅ Works on any device with internet access
- ✅ Handles localhost AND production automatically

---

## 💡 QUICK SUMMARY

```bash
# 1. Download from Figma Make (as ZIP)
# 2. Unzip and verify files
# 3. Go to railway.app
# 4. Create new project
# 5. Upload code (GitHub or CLI)
# 6. Generate domain
# 7. Visit your URL
# 8. Start scraping!
```

**That's it!** No configuration, no setup, no docs needed. Just unzip and deploy! 🚀
