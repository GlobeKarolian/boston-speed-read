#!/usr/bin/env python3
import json
import os
import time
import re
from datetime import datetime, timedelta
import feedparser
from openai import OpenAI
import requests
from typing import List, Dict, Optional

def load_historical_articles():
    """Load existing historical articles"""
    try:
        with open('news-history.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('articles', [])
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Error loading history: {e}")
        return []

def save_historical_articles(articles):
    """Save articles to history file"""
    try:
        # Load existing history
        existing = load_historical_articles()
        
        # Create a set of existing article identifiers (title + date)
        existing_ids = set()
        for article in existing:
            article_id = f"{article['title']}_{article.get('pubDate', '')}"
            existing_ids.add(article_id)
        
        # Add new articles that don't exist
        new_count = 0
        for article in articles:
            article_id = f"{article['title']}_{article.get('pubDate', '')}"
            if article_id not in existing_ids:
                existing.append(article)
                new_count += 1
        
        # Sort by date (newest first)
        existing.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
        
        # Keep only last 500 articles to prevent file from getting too large
        existing = existing[:500]
        
        # Save to history file
        with open('news-history.json', 'w', encoding='utf-8') as f:
            json.dump({
                'lastUpdated': datetime.now().isoformat(),
                'articles': existing,
                'totalArticles': len(existing)
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Added {new_count} new articles to history (total: {len(existing)})")
        
    except Exception as e:
        print(f"Error saving history: {e}")

def validate_api_key():
    """Validate OpenAI API key"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return None
    print(f"API key found: {api_key[:7]}...{api_key[-4:]}")
    return api_key

def fetch_rss_feed(url: str, count: int = 12) -> List[Dict]:
    """Fetch and parse RSS feed - increased to 12 for more content"""
    print(f"\nFetching RSS feed from {url}")
    
    try:
        response = requests.get(url, timeout=10)
        feed = feedparser.parse(response.text)
    except:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"Failed to fetch feed: {e}")
            return []
    
    articles = []
    for entry in feed.entries[:count]:
        # Get and clean description
        description = entry.get('description', entry.get('summary', ''))
        # Remove HTML tags
        clean_desc = re.sub(r'<[^>]+>', '', description)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        
        # Get full content if available
        content = ""
        if hasattr(entry, 'content'):
            content = entry.content[0].value if entry.content else ""
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\s+', ' ', content).strip()
        
        article = {
            'title': entry.get('title', 'No title'),
            'link': entry.get('link', ''),
            'description': clean_desc[:1500],
            'content': content[:2000] if content else clean_desc[:2000],
            'pubDate': entry.get('published', entry.get('pubDate', ''))
        }
        articles.append(article)
    
    print(f"✓ Found {len(articles)} articles")
    return articles

def generate_ai_summary(client: OpenAI, article: Dict) -> Optional[List[str]]:
    """Generate engaging AI summary with curiosity gap"""
    print(f"\nGenerating summary for: {article['title'][:60]}...")
    
    content = article['content'] if article['content'] else article['description']
    
    prompt = f"""You are a skilled Boston news journalist creating engaging, informative bullet-point summaries for busy readers.

Article Title: {article['title']}

Article Content: {content[:1200]}

Create exactly 3 compelling bullet points that:
1. First bullet: Capture the MAIN NEWS - what happened and why it matters to Boston residents
2. Second bullet: Provide KEY DETAILS - important facts, numbers, quotes, or context that readers need to know  
3. Third bullet: Create a CURIOSITY GAP - tease something surprising, controversial, or unexpected from the article that makes readers want to click

Requirements:
- Make each bullet point 15-25 words
- Use active voice and strong verbs
- Include specific details (names, numbers, dates, locations) when available
- The third bullet should create intrigue without giving away the answer
- Use phrases like "reveals why", "unexpected reason", "surprising connection", "what happened next", "the real reason"
- Don't just repeat the headline - add NEW information and context
- Return ONLY a JSON array of 3 strings

Example format:
["Mayor Wu announces $50M investment in affordable housing, targeting 1,000 new units in Roxbury and Dorchester by 2026", "The initiative includes partnerships with local developers and prioritizes families earning below $75,000 annually", "But one Boston neighborhood surprisingly rejected the plan - and their reason has city officials scrambling"]

More curiosity gap examples for bullet 3:
- "The unexpected company behind the deal has ties to a controversial 2019 Boston development"
- "What the victim's family said in court left even the prosecutor visibly shaken"  
- "The Red Sox's unusual strategy actually worked before - but only once in MLB history"
- "City councilors discovered a loophole that could change everything about Boston's housing crisis"

DO NOT use generic curiosity gaps. Make them specific to the actual article content."""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a Boston news editor creating engaging, fact-rich summaries. Return only a JSON array of exactly 3 bullet points."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.7,
            timeout=20
        )
        
        content = response.choices[0].message.content.strip()
        content = content.replace('```json', '').replace('```', '').strip()
        
        try:
            points = json.loads(content)
            if isinstance(points, list) and len(points) == 3:
                print(f"  ✓ Generated engaging AI summary")
                return points
        except json.JSONDecodeError:
            lines = content.split('\n')
            points = []
            for line in lines:
                clean = re.sub(r'^[\-\*\•\"]\s*', '', line.strip())
                clean = re.sub(r'\"$', '', clean)
                if clean and len(clean) > 10:
                    points.append(clean)
            
            if len(points) >= 3:
                print(f"  ✓ Extracted {len(points)} points from response")
                return points[:3]
        
        print(f"  ⚠ Invalid response format")
        return None
        
    except Exception as e:
        print(f"  ✗ AI generation failed: {str(e)[:100]}")
        return None

def generate_fallback_summary(article: Dict) -> List[str]:
    """Generate better fallback summaries with curiosity gap when AI fails"""
    import random  # Import at function level if not imported globally
    
    title = article['title']
    content = article['content'] if article['content'] else article['description']
    
    sentences = re.split(r'[.!?]+', content)
    clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    summary = []
    
    # First bullet - main news
    if "Red Sox" in title or "Celtics" in title or "Patriots" in title or "Bruins" in title:
        summary.append(f"Boston sports update: {title[:70]}")
    elif any(word in title.lower() for word in ['mayor', 'city', 'council', 'police', 'fire']):
        summary.append(f"Local government news: {title[:70]}")
    else:
        summary.append(f"Breaking: {title[:70]}")
    
    # Second bullet - key detail
    if clean_sentences:
        summary.append(clean_sentences[0][:80])
    else:
        summary.append("Story developing with updates expected throughout the day")
    
    # Third bullet - curiosity gap
    curiosity_gaps = [
        "The surprising detail that has Boston residents talking is revealed inside",
        "What happens next could affect thousands of Boston area families",
        "The unexpected reason behind this decision changes everything",
        "Local officials reveal the one thing nobody saw coming",
        "The real story involves a twist that even surprised investigators"
    ]
    summary.append(random.choice(curiosity_gaps))
    
    return summary

def main():
    print("=" * 60)
    print("Boston News Summarizer - With History Accumulation")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Validate API key
    api_key = validate_api_key()
    
    # Initialize OpenAI client if key exists
    client = None
    if api_key:
        try:
            client = OpenAI(api_key=api_key, timeout=30.0)
            test = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5
            )
            print("✓ OpenAI API connected successfully")
        except Exception as e:
            print(f"✗ OpenAI API connection failed: {str(e)[:100]}")
            client = None
    
    # Fetch articles
    articles = fetch_rss_feed("https://www.boston.com/feed/bdc-msn-rss", count=12)
    
    if not articles:
        print("\nNo articles found")
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {'error': 'No articles found'}
        }
    else:
        print(f"\n{'=' * 60}")
        print(f"Processing {len(articles)} articles...")
        print(f"{'=' * 60}")
        
        processed = []
        ai_summaries = 0
        fallback_summaries = 0
        
        for i, article in enumerate(articles):
            print(f"\n[Article {i+1}/{len(articles)}]")
            
            summary = None
            
            # Try AI summary if client available
            if client:
                summary = generate_ai_summary(client, article)
                if summary:
                    ai_summaries += 1
                    if i < len(articles) - 1:
                        time.sleep(1.5)
            
            # Use fallback if AI failed
            if not summary:
                summary = generate_fallback_summary(article)
                fallback_summaries += 1
                print("  Using fallback summary")
            
            processed.append({
                'title': article['title'],
                'link': article['link'],
                'pubDate': article['pubDate'],
                'summary': summary
            })
        
        # Save to history
        save_historical_articles(processed)
        
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed,
            'stats': {
                'total_articles': len(processed),
                'ai_summaries': ai_summaries,
                'fallback_summaries': fallback_summaries,
                'success_rate': f"{(ai_summaries/len(processed)*100):.1f}%" if processed else "0%"
            }
        }
    
    # Save current batch
    with open('news-data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 60}")
    print("SUMMARY GENERATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"✓ Total articles: {len(output.get('articles', []))}")
    print(f"✓ AI summaries: {ai_summaries}")
    if fallback_summaries > 0:
        print(f"⚠ Fallback summaries: {fallback_summaries}")
    print(f"→ Success rate: {output.get('stats', {}).get('success_rate', '0%')}")
    print(f"→ Current batch saved to news-data.json")
    print(f"→ History saved to news-history.json")
    
    # Show total articles in history
    history = load_historical_articles()
    print(f"→ Total articles in history: {len(history)}")
    print(f"{'=' * 60}\n")
    
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        print(f"Fatal error: {e}")
        with open('news-data.json', 'w') as f:
            json.dump({
                'lastUpdated': datetime.now().isoformat(),
                'articles': [],
                'stats': {'error': str(e)}
            }, f, indent=2)
        exit(0)
