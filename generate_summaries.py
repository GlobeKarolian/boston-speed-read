#!/usr/bin/env python3
"""
Boston.com Speed Read - News Summary Generator
Fetches Boston.com RSS feed and generates concise, non-clickbait summaries
"""

import json
import os
import sys
import feedparser
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional
import hashlib
import time

# Configuration
RSS_FEED_URL = "https://www.boston.com/feed/"
MAX_ARTICLES = 15
MAX_HISTORY = 50
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = "gpt-4o-mini"  # Cost-effective model

def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch and parse RSS feed"""
    try:
        feed = feedparser.parse(url)
        if feed.bozo:
            print(f"Warning: Feed parsing issues detected: {feed.bozo_exception}")
        
        articles = []
        for entry in feed.entries[:MAX_ARTICLES]:
            article = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "pubDate": entry.get("published", ""),
                "description": entry.get("summary", ""),
                "id": hashlib.md5(entry.get("link", "").encode()).hexdigest()
            }
            articles.append(article)
        
        return articles
    except Exception as e:
        print(f"Error fetching RSS feed: {e}")
        return []

def generate_summary(article: Dict) -> Optional[Dict]:
    """Generate concise summary bullets using OpenAI API"""
    if not OPENAI_API_KEY:
        print("Warning: OPENAI_API_KEY not set, using fallback summaries")
        return generate_fallback_summary(article)
    
    prompt = f"""You are a Boston local news summarizer. Create exactly 3 concise, concrete bullet points about this article.

Rules:
- Each bullet must be 10-20 words max
- Start bullets with action words or "What/Why/Who/Where"
- Include specific numbers, names, dates when available
- No clickbait, no "Find out why", no teasers
- Focus on LOCAL IMPACT for Boston residents
- Be direct and informative

Article Title: {article['title']}
Description: {article.get('description', '')[:500]}

Respond with ONLY a JSON object in this exact format:
{{
  "summary": [
    "First concrete fact or what happened",
    "Second specific detail with number/name if available", 
    "Third key impact or consequence"
  ],
  "hookType": "LOCAL_IMPACT"
}}"""

    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are a concise news summarizer. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Parse JSON from response
            try:
                summary_data = json.loads(content)
                return {
                    "summary": summary_data.get("summary", [])[:3],
                    "hookType": summary_data.get("hookType", "LOCAL_IMPACT")
                }
            except json.JSONDecodeError:
                print(f"Failed to parse JSON response for: {article['title']}")
                return generate_fallback_summary(article)
        else:
            print(f"OpenAI API error {response.status_code}: {response.text}")
            return generate_fallback_summary(article)
            
    except Exception as e:
        print(f"Error generating summary: {e}")
        return generate_fallback_summary(article)

def generate_fallback_summary(article: Dict) -> Dict:
    """Generate basic summary when AI is unavailable"""
    title = article.get('title', 'News Update')
    desc = article.get('description', '')[:100]
    
    return {
        "summary": [
            f"Update: {title[:50]}",
            f"Details: {desc[:50] if desc else 'Check article for more information'}",
            "Visit Boston.com for complete coverage"
        ],
        "hookType": "NEWS_UPDATE"
    }

def load_existing_data(filename: str) -> Dict:
    """Load existing JSON data file"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"articles": [], "lastUpdated": None}

def save_data(filename: str, data: Dict):
    """Save data to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved {len(data.get('articles', []))} articles to {filename}")
    except Exception as e:
        print(f"Error saving {filename}: {e}")
        raise

def main():
    """Main execution function"""
    print("=== Boston Speed Read - News Summary Generator ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    # Check for API key
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not set - will use fallback summaries")
        print("   Set the secret in your GitHub repo: Settings > Secrets > Actions")
    
    # Fetch articles
    print(f"\nFetching RSS feed from Boston.com...")
    articles = fetch_rss_feed(RSS_FEED_URL)
    
    if not articles:
        print("❌ No articles fetched. Exiting.")
        sys.exit(1)
    
    print(f"✓ Fetched {len(articles)} articles")
    
    # Load existing history
    history_data = load_existing_data("news-history.json")
    existing_ids = {a.get("id") for a in history_data.get("articles", []) if a.get("id")}
    
    # Process articles
    processed_articles = []
    new_count = 0
    
    for i, article in enumerate(articles, 1):
        article_id = article.get("id")
        
        # Skip if already processed
        if article_id in existing_ids:
            print(f"  [{i}/{len(articles)}] Skipping (already processed): {article['title'][:50]}...")
            continue
        
        print(f"  [{i}/{len(articles)}] Processing: {article['title'][:50]}...")
        
        # Generate summary
        summary_data = generate_summary(article)
        
        if summary_data:
            processed_article = {
                **article,
                **summary_data
            }
            processed_articles.append(processed_article)
            new_count += 1
            
            # Rate limiting for API calls
            if OPENAI_API_KEY and i < len(articles):
                time.sleep(0.5)  # Avoid rate limits
    
    print(f"\n✓ Processed {new_count} new articles")
    
    # Update current data
    current_data = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "articles": processed_articles[:10],  # Keep top 10 for current display
        "stats": {
            "totalProcessed": new_count,
            "feedSize": len(articles),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }
    
    # Save current data
    save_data("news-data.json", current_data)
    
    # Update history (prepend new articles, keep MAX_HISTORY items)
    if new_count > 0:
        all_history = processed_articles + history_data.get("articles", [])
        history_data = {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "articles": all_history[:MAX_HISTORY],
            "totalArticles": len(all_history[:MAX_HISTORY])
        }
        save_data("news-history.json", history_data)
    
    print("\n✅ Summary generation complete!")
    print(f"   - New articles: {new_count}")
    print(f"   - Total in history: {len(history_data.get('articles', []))}")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
