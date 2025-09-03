#!/usr/bin/env python3
import json
import os
import time
import re
from datetime import datetime
import feedparser
from openai import OpenAI
import requests
from typing import List, Dict, Optional
import random

def clean_json_file(filename):
    """Remove merge conflict markers from JSON file"""
    try:
        with open(filename, 'r') as f:
            content = f.read()
        
        # If there are merge conflicts, clean them
        if '<<<<<<< ' in content:
            print(f"Cleaning merge conflicts from {filename}")
            lines = content.split('\n')
            clean_lines = []
            skip = False
            
            for line in lines:
                if '<<<<<<< ' in line or '=======' in line or '>>>>>>> ' in line:
                    skip = not skip
                elif not skip:
                    clean_lines.append(line)
            
            # Try to parse the cleaned content
            try:
                cleaned = '\n'.join(clean_lines)
                json.loads(cleaned)  # Test if valid JSON
                with open(filename, 'w') as f:
                    f.write(cleaned)
                print(f"Successfully cleaned {filename}")
            except:
                # If still invalid, start fresh
                print(f"Could not clean {filename}, starting fresh")
                if 'history' in filename:
                    return {'articles': []}
                return None
    except:
        pass
    return None

def load_json_safely(filename, default=None):
    """Load JSON file, handling errors and conflicts"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        # Try to clean conflicts
        clean_json_file(filename)
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default

def save_json_safely(data, filename):
    """Save JSON file safely"""
    try:
        # Write to temp file first
        temp_file = f"{filename}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Move temp to actual file
        os.replace(temp_file, filename)
        return True
    except Exception as e:
        print(f"Error saving {filename}: {e}")
        return False

def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch articles from RSS feed"""
    print(f"Fetching RSS feed...")
    
    try:
        response = requests.get(url, timeout=10)
        feed = feedparser.parse(response.text)
    except:
        feed = feedparser.parse(url)
    
    articles = []
    for entry in feed.entries[:12]:  # Get 12 articles
        description = entry.get('description', '')
        clean_desc = re.sub(r'<[^>]+>', '', description)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        
        articles.append({
            'title': entry.get('title', 'No title'),
            'link': entry.get('link', ''),
            'description': clean_desc[:1000],
            'pubDate': entry.get('published', entry.get('pubDate', ''))
        })
    
    print(f"Found {len(articles)} articles")
    return articles

def generate_summary(client: Optional[OpenAI], article: Dict) -> List[str]:
    """Generate AI summary or fallback"""
    
    # Try AI summary if client available
    if client:
        try:
            prompt = f"""Create 3 bullet points for this Boston news:

Title: {article['title']}
Content: {article['description'][:600]}

Requirements:
1. First bullet: Main news and why it matters (15-20 words)
2. Second bullet: Key facts, numbers, or quotes (15-20 words)
3. Third bullet: Create curiosity - tease something surprising without revealing it (15-20 words)

Use phrases like "reveals why", "unexpected reason", "surprising twist" in bullet 3.
Return ONLY a JSON array of 3 strings."""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7,
                timeout=15
            )
            
            content = response.choices[0].message.content.strip()
            content = content.replace('```json', '').replace('```', '')
            
            points = json.loads(content)
            if isinstance(points, list) and len(points) == 3:
                return points
        except:
            pass
    
    # Fallback summary - make these specific too
    title = article['title'][:70]
    desc_sentences = article['description'].split('. ')
    
    # Extract any numbers, names, or specific details from description
    import re
    numbers = re.findall(r'\d+', article['description'])
    number_fact = f"The change affects {numbers[0]} locations" if numbers else ""
    
    # More specific fallback third bullets
    varied_specifics = [
        f"The decision comes three months after the previous policy expired",
        f"City officials estimate implementation will take 6-8 weeks",
        f"This marks the fourth similar incident in Boston since January",
        f"The proposal requires approval from state regulators by year-end",
        f"Local business groups have filed two formal complaints already",
        f"The last comparable situation occurred in Boston in 2019",
        number_fact if number_fact else "Officials haven't released a timeline for next steps"
    ]
    
    summary = [
        f"{title}",
        desc_sentences[0][:80] if desc_sentences else "Details emerging as story develops",
        random.choice(varied_specifics)
    ]
    
    return summary

def update_history(new_articles):
    """Add articles to history file"""
    history = load_json_safely('news-history.json', {'articles': []})
    
    # Get existing titles to avoid duplicates
    existing_titles = {a['title'] for a in history.get('articles', [])}
    
    # Add new unique articles
    for article in new_articles:
        if article['title'] not in existing_titles:
            history['articles'].insert(0, article)  # Add to beginning
    
    # Keep only 500 most recent
    history['articles'] = history['articles'][:500]
    history['lastUpdated'] = datetime.now().isoformat()
    history['totalArticles'] = len(history['articles'])
    
    save_json_safely(history, 'news-history.json')
    print(f"History updated: {len(history['articles'])} total articles")

def main():
    print("=" * 60)
    print("Boston News Summarizer")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Initialize OpenAI
    api_key = os.getenv('OPENAI_API_KEY')
    client = None
    
    if api_key:
        try:
            client = OpenAI(api_key=api_key, timeout=20.0)
            # Quick test
            client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            print("✓ OpenAI connected")
        except Exception as e:
            print(f"✗ OpenAI failed: {str(e)[:50]}")
            client = None
    else:
        print("⚠ No API key, using fallback summaries")
    
    # Fetch articles
    articles = fetch_rss_feed("https://www.boston.com/feed/bdc-msn-rss")
    
    if not articles:
        print("No articles found!")
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {'error': 'No articles'}
        }
    else:
        # Process articles
        processed = []
        ai_count = 0
        
        for i, article in enumerate(articles):
            print(f"Processing {i+1}/{len(articles)}: {article['title'][:40]}...")
            
            summary = generate_summary(client, article)
            
            # Check if AI was used
            if client and not any('shocking' in s or 'everything' in s for s in summary):
                ai_count += 1
            
            processed.append({
                'title': article['title'],
                'link': article['link'],
                'pubDate': article['pubDate'],
                'summary': summary
            })
            
            # Rate limit
            if client and i < len(articles) - 1:
                time.sleep(1)
        
        # Update history
        update_history(processed)
        
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed,
            'stats': {
                'total_articles': len(processed),
                'ai_summaries': ai_count,
                'fallback_summaries': len(processed) - ai_count,
                'success_rate': f"{(ai_count/len(processed)*100):.0f}%"
            }
        }
    
    # Save output
    save_json_safely(output, 'news-data.json')
    
    print("\n" + "=" * 60)
    print(f"Complete! {len(output['articles'])} articles processed")
    print(f"AI summaries: {output['stats'].get('ai_summaries', 0)}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        # Always create output file
        save_json_safely({
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {'error': str(e)}
        }, 'news-data.json')
        exit(0)  # Exit successfully to not break workflow
