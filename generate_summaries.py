#!/usr/bin/env python3
import json
import os
import time
import re
from datetime import datetime
import feedparser
from openai import OpenAI
import requests
from typing import List, Dict

def test_connectivity():
    """Test basic internet connectivity"""
    print("\nTesting connectivity...")
    
    # Test 1: Can we reach common sites?
    test_urls = [
        ("Google", "https://www.google.com"),
        ("OpenAI", "https://api.openai.com"),
        ("Boston.com", "https://www.boston.com")
    ]
    
    for name, url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            print(f"✓ {name}: Reachable (Status: {response.status_code})")
        except Exception as e:
            print(f"✗ {name}: Failed - {str(e)[:50]}")
    
    # Test 2: Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("✗ API Key: NOT FOUND in environment")
        return False
    else:
        # Mask the key for security
        masked = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 11 else "INVALID"
        print(f"✓ API Key: Found ({masked})")
        
        # Check format
        if not api_key.startswith('sk-'):
            print("  ⚠ Warning: Key doesn't start with 'sk-'")
        
        return True

def test_openai_api():
    """Test OpenAI API with minimal request"""
    print("\nTesting OpenAI API...")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("✗ Cannot test - no API key")
        return False
    
    try:
        # Test with a simple completion
        client = OpenAI(api_key=api_key, timeout=10.0)
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Reply with just 'OK'"}],
            max_tokens=5
        )
        
        print(f"✓ OpenAI API working! Response: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"✗ OpenAI API failed: {error_str[:200]}")
        
        # Provide specific guidance based on error
        if "401" in error_str or "Incorrect API key" in error_str:
            print("\n  → Fix: Your API key is invalid. Please check:")
            print("     1. The key is correctly copied (no extra spaces)")
            print("     2. The key hasn't been revoked")
            print("     3. Generate a new key at https://platform.openai.com/api-keys")
        elif "429" in error_str:
            print("\n  → Fix: Rate limit exceeded. Wait a few minutes or check your OpenAI usage.")
        elif "Connection" in error_str or "timeout" in error_str:
            print("\n  → Fix: Network issue. OpenAI might be down or GitHub Actions might be blocked.")
            print("     Consider using a different approach or proxy.")
        elif "insufficient_quota" in error_str:
            print("\n  → Fix: Your OpenAI account has no credits. Add billing at https://platform.openai.com/account/billing")
        
        return False

def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch and parse RSS feed"""
    print(f"\nFetching RSS feed from {url}")
    
    try:
        # Try direct request first
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
    except Exception as e:
        print(f"  Direct fetch failed: {e}, trying feedparser...")
        try:
            feed = feedparser.parse(url)
        except Exception as e2:
            print(f"  Feedparser also failed: {e2}")
            return []
    
    articles = []
    for entry in feed.entries[:3]:  # Just get 3 for testing
        description = entry.get('description', entry.get('summary', ''))
        clean_description = re.sub(r'<[^>]+>', '', description)
        clean_description = re.sub(r'\s+', ' ', clean_description).strip()
        
        article = {
            'title': entry.get('title', 'No title'),
            'link': entry.get('link', ''),
            'description': clean_description[:500],
            'pubDate': entry.get('published', entry.get('pubDate', '')),
        }
        articles.append(article)
    
    print(f"✓ Found {len(articles)} articles")
    return articles

def generate_summary_with_fallback(client: OpenAI, article: Dict) -> List[str]:
    """Try to generate summary with detailed error reporting"""
    print(f"\nGenerating summary for: {article['title'][:60]}...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Create 3 bullet points, return as JSON array."},
                {"role": "user", "content": f"Summarize: {article['title']}. {article['description'][:300]}"}
            ],
            max_tokens=150,
            temperature=0.7,
            timeout=15
        )
        
        content = response.choices[0].message.content
        print(f"  Got response: {content[:100]}...")
        
        # Try to parse JSON
        try:
            points = json.loads(content)
            if isinstance(points, list):
                return points[:3]
        except:
            pass
        
        # Extract any bullet points
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if lines:
            return lines[:3]
            
    except Exception as e:
        print(f"  Error: {str(e)[:100]}")
    
    # Fallback
    return [
        f"Latest: {article['title'][:70]}",
        "Summary pending - check back soon",
        "Read full story below"
    ]

def main():
    print("=" * 60)
    print("Boston News Summarizer - DEBUG MODE")
    print("=" * 60)
    
    # Run connectivity tests
    if not test_connectivity():
        print("\n❌ Connectivity issues detected!")
    
    # Test OpenAI specifically
    api_works = test_openai_api()
    
    if not api_works:
        print("\n❌ OpenAI API is not working. Creating fallback content...")
        
    # Fetch articles regardless
    articles = fetch_rss_feed("https://www.boston.com/feed/bdc-msn-rss")
    
    if not articles:
        print("\n❌ No articles fetched")
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {'error': 'No articles fetched'}
        }
    else:
        # Process articles
        processed = []
        
        if api_works:
            # Only try API if it's working
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'), timeout=15.0)
            
            for article in articles:
                summary = generate_summary_with_fallback(client, article)
                processed.append({
                    'title': article['title'],
                    'link': article['link'],
                    'pubDate': article['pubDate'],
                    'summary': summary
                })
                time.sleep(1)  # Rate limiting
        else:
            # Use fallbacks for all
            for article in articles:
                processed.append({
                    'title': article['title'],
                    'link': article['link'],
                    'pubDate': article['pubDate'],
                    'summary': [
                        f"Breaking: {article['title'][:70]}",
                        "AI summaries temporarily unavailable",
                        "Click for full story from Boston.com"
                    ]
                })
        
        output = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed,
            'stats': {
                'total': len(processed),
                'api_working': api_works
            }
        }
    
    # Save output
    with open('news-data.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"Output saved to news-data.json")
    print(f"API Status: {'✓ Working' if api_works else '✗ Failed'}")
    print(f"Articles: {len(output.get('articles', []))}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
