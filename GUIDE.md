# 🚀 Complete Step-by-Step Guide — Zero Experience Needed

This guide takes you from zero to a live submitted bot in ~30 minutes.
Uses Google Gemini API — **completely FREE, no credit card**.

---

## STEP 1 — Install Python (skip if already installed)

1. Go to https://www.python.org/downloads/
2. Click the big yellow "Download Python 3.12.x" button
3. Run the installer
4. **IMPORTANT**: Check the box that says "Add Python to PATH"
5. Click Install Now

**Check it worked**: Open a terminal (CMD on Windows / Terminal on Mac) and type:
```
python --version
```
You should see something like: `Python 3.12.3`

---

## STEP 2 — Get your FREE Gemini API Key

1. Go to: https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Click "Create API key in new project"
5. Copy the key that looks like: `AIzaSyABC123...`
6. Save it somewhere — you'll need it in Step 4

**It's free. No credit card. The free tier allows 15 requests/min and 1500/day — more than enough.**

---

## STEP 3 — Download and set up the project

1. Download the `vera-bot.zip` file (from this chat)
2. Right-click → Extract All / Unzip it
3. You'll get a folder called `vera-bot`
4. Open your terminal and navigate to that folder:

**On Windows:**
```
cd Downloads\vera-bot
```

**On Mac/Linux:**
```
cd Downloads/vera-bot
```

---

## STEP 4 — Install dependencies

In your terminal (inside the vera-bot folder), run:
```
pip install -r requirements.txt
```

Wait for it to finish (downloads ~5 packages). You'll see a lot of text — that's normal.

---

## STEP 5 — Set your API key

Open the `.env` file in Notepad/any text editor.

Change this line:
```
GEMINI_API_KEY=AIzaSy_YOUR_KEY_HERE
```

To your actual key:
```
GEMINI_API_KEY=AIzaSyABC123yourActualKeyHere
```

Save the file.

---

## STEP 6 — Run the bot locally

In your terminal, run:
```
uvicorn main:app --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Your bot is now running! Leave this terminal open.

---

## STEP 7 — Test it works

Open a NEW terminal window (keep the first one running), navigate to the vera-bot folder, and run:
```
python test_bot.py
```

You should see mostly ✅. The test will call Gemini AI and you'll see an actual composed message.

**If you see errors**: Double-check your API key in the .env file.

---

## STEP 8 — Deploy to the internet (so magicpin can reach it)

You need a **public URL** for submission. Use **Render** (free hosting).

### Option A: Render (Recommended — completely free)

1. Create a free account at https://render.com (sign up with GitHub)
2. Create a GitHub account if you don't have one: https://github.com
3. Create a new GitHub repository:
   - Go to github.com → New repository → Name it "vera-bot" → Create
4. Upload your files to GitHub:
   - Click "uploading an existing file"
   - Drag and drop ALL files from your vera-bot folder
   - Click "Commit changes"
5. In Render:
   - Click "New" → "Web Service"
   - Connect your GitHub account → Select vera-bot repository
   - Fill in settings:
     - **Name**: vera-bot
     - **Runtime**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Click "Advanced" → "Add Environment Variable":
     - Key: `GEMINI_API_KEY`
     - Value: your API key
   - Click "Create Web Service"
6. Wait 2-3 minutes for deployment
7. Your URL will be: `https://vera-bot-XXXX.onrender.com`

### Option B: ngrok (Fastest — for local testing only)

1. Go to https://ngrok.com and create a free account
2. Download ngrok from https://ngrok.com/download
3. In a new terminal: `ngrok http 8000`
4. Copy the URL shown (like `https://abc123.ngrok-free.app`)

Note: ngrok URLs expire after 2 hours on the free plan. Use Render for final submission.

---

## STEP 9 — Verify your deployed bot

Replace YOUR_URL with your Render/ngrok URL:
```
curl https://YOUR_URL/v1/healthz
```

You should see: `{"status":"ok",...}`

---

## STEP 10 — Submit to magicpin

1. Go to the magicpin challenge submission page
2. Fill in:
   - **Full name**: your name
   - **Email**: your email
   - **Phone**: your phone
   - **Submission URL**: `https://vera-bot-XXXX.onrender.com`
   - **LinkedIn**: (optional)
3. Submit!

**Keep your bot running until May 5** — the judge harness will test it for the next ~48 hours.

---

## Troubleshooting

**"pip not found"**: Use `pip3` instead of `pip`

**"ModuleNotFoundError"**: Run `pip install -r requirements.txt` again

**"GEMINI_API_KEY not set"**: You need to load the .env file. Either:
- Set it manually: `set GEMINI_API_KEY=your_key` (Windows) or `export GEMINI_API_KEY=your_key` (Mac/Linux)
- Or add this to the TOP of main.py: `from dotenv import load_dotenv; load_dotenv()`

**Render build failing**: Make sure all files are uploaded to GitHub, especially requirements.txt

**Bot times out on Render free tier**: The free tier sleeps after 15 min. Upgrade to Starter ($7/mo) if the judge marks your bot as offline, or use Railway instead.

---

## Quick Reference — What your bot does

When magicpin's judge sends a trigger (like "190 people searching for Dental Check Up"), your bot:
1. Looks up the merchant's data (Dr. Meera, her offers, her location)
2. Looks up the category (dentist tone, vocabulary rules)
3. Calls Gemini AI with all this context
4. Returns a specific, useful WhatsApp message like:
   "Dr. Meera, JIDA Oct: 3-mo fluoride recall cuts caries 38% better (n=2,100). Relevant to your 124 high-risk patients. Want me to pull the abstract + draft a patient WhatsApp?"

The judge scores it on: specificity, category fit, merchant fit, trigger relevance, and engagement compulsion.
