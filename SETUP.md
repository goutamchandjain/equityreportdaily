# India Equity Daily Scan — GitHub Actions Setup

This runs every weekday at **7:00 AM IST** automatically. Claude fetches live market data, generates a full HTML report, and emails it to you — no Cowork session needed.

---

## Step 1 — Create a GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Name it something like `india-equity-scan`
3. Set it to **Private** (keeps your API keys safe)
4. Do **not** initialise with a README (you'll push from local)

---

## Step 2 — Push this folder to GitHub

Open Terminal, navigate to this folder, and run:

```bash
cd ~/Equity
git init
git add .
git commit -m "Initial commit — India equity scan"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/india-equity-scan.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Step 3 — Get your Gmail App Password

This is a special password just for the script (not your normal Gmail password).

1. Go to your Google Account → **Security**
2. Make sure **2-Step Verification** is ON
3. Search for "App passwords" → select it
4. Under "Select app" choose **Mail**, under device choose **Other** → type `equity-scan`
5. Click **Generate** — copy the 16-character password shown

---

## Step 4 — Add GitHub Secrets

Go to your repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets:

| Secret name          | Value                                      |
|----------------------|--------------------------------------------|
| `ANTHROPIC_API_KEY`  | Your Anthropic API key (from console.anthropic.com) |
| `GMAIL_USER`         | `goutam.bang@gmail.com`                    |
| `GMAIL_APP_PASSWORD` | The 16-char App Password from Step 3       |

---

## Step 5 — Enable GitHub Actions

1. In your repo, click the **Actions** tab
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. The workflow will now run automatically at 7:00 AM IST Mon–Fri

---

## Manual trigger (run anytime)

1. Go to **Actions** tab in your repo
2. Click **"🇮🇳 India Equity Daily Scan"** in the left sidebar
3. Click **"Run workflow"** → **"Run workflow"** (green button)

The report will be emailed to `goutam.bang@gmail.com` within ~2 minutes.

---

## What happens each run

```
[1/5] Fetch live index data (Nifty, Sensex, Dow, Nasdaq, Nikkei, Hang Seng…)
[2/5] Fetch 25 key NSE stock prices + 52W high/low
[3/5] Pull news headlines from NDTV Profit, ET Markets, Moneycontrol RSS
[4/5] Call Claude API → generates full dark-theme HTML report (8 sections)
[5/5] Email to goutam.bang@gmail.com via Gmail SMTP
```

The HTML report is also saved as a **GitHub Actions artifact** (downloadable from the Actions tab, kept for 30 days).

---

## Costs

| Service         | Cost                                                    |
|-----------------|---------------------------------------------------------|
| GitHub Actions  | **Free** (2,000 minutes/month on free tier — this uses ~2 min/day) |
| Anthropic API   | ~$0.03–0.05 per report (claude-opus-4-6)                |
| Gmail SMTP      | **Free**                                                |

Monthly cost: roughly **₹80–120/month** in API calls for 22 trading days.

---

## Folder structure

```
Equity/
├── .github/
│   └── workflows/
│       └── india_equity_scan.yml   ← GitHub Actions schedule
├── scripts/
│   ├── generate_report.py          ← Main script
│   └── requirements.txt            ← Python dependencies
├── output/                         ← Reports saved here (git-ignored)
└── SETUP.md                        ← This file
```

---

## Troubleshooting

**Email not arriving?**
- Check the Actions tab — click the latest run to see logs
- Verify all 3 secrets are set correctly (no extra spaces)
- Make sure the Gmail App Password is the 16-char one (without spaces)

**"Authentication failed" error?**
- Regenerate the App Password and update the GitHub secret

**Market data showing zeros?**
- yfinance occasionally has downtime; the report will still generate using Claude's knowledge
- The next day's run will have fresh data
