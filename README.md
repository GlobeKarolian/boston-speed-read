# 🗞️ Boston Speed Read

**Concrete, non-clickbaity news bullets from Boston.com**

A GitHub Actions-powered news aggregator that fetches Boston.com RSS feeds and generates concise, actionable summaries using AI.

## 🎯 Features

- **Auto-updates every 2 hours** via GitHub Actions
- **No clickbait** - Just concrete facts and local impact
- **3 bullet points per story** - Each 10-20 words max
- **Mobile-friendly** static site hosted on GitHub Pages
- **History tracking** - Keeps record of past articles
- **Fallback mode** - Works even without OpenAI API key

## 🚀 Quick Setup

### 1. Fork or Use This Template

Click "Use this template" or fork this repository to your GitHub account.

### 2. Set Up OpenAI API Key (Optional but Recommended)

1. Go to your repo's **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `OPENAI_API_KEY`
4. Value: Your OpenAI API key (get one at [platform.openai.com](https://platform.openai.com))
5. Click **Add secret**

> **Note**: The system will still work without an API key using fallback summaries, but AI summaries are much better.

### 3. Enable GitHub Pages

1. Go to **Settings** → **Pages**
2. Under "Source", select **Deploy from a branch**
3. Choose **main
