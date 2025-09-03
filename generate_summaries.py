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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def validate_api_key():
    """Validate that the OpenAI API key is set and appears valid"""
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set your OpenAI API key in GitHub Secrets")
        return None
    
    if not api_key.startswith('sk-'):
        print("WARNING: API key doesn't start with 'sk-', it might be invalid")
    
    print(f"API key found: sk-...{api_key[-4:]}")
    return api_key

def test_openai_connection(client):
    """Test if we can connect to OpenAI API"""
    print("\nTesting OpenAI API connection...")
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'test successful'"}],
            max_tokens=10,
            timeout=10
        )
        print("✓ OpenAI API connection successful")
        return True
    except Exception as e:
        print(f"✗ OpenAI API connection failed: {str(e)}")
        if "401" in str(e):
            print("  → Authentication failed. Check your API key.")
        elif "429" in str(e):
            print("  → Rate limit exceeded. Wait a moment and try again.")
        elif "timeout" in str(e):
            print("  → Connection timeout. OpenAI might be experiencing issues.")
        return False

def create_session_with_retries():
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch and parse RSS feed with retry logic"""
    print(f"\nFetching RSS feed from {url}")
    
    session = create_session_with_retries()
    
    for attempt in range(3):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            break
        except Exception as e:
            print(f"  Attempt {attempt + 1}/3 failed to fetch RSS: {e}")
            if attempt == 2:
                # Fallback to feedparser direct parsing
                try:
                    feed = feedparser.parse(url)
                except Exception as fe:
                    print(f"  Direct feedparser also failed: {fe}")
                    return []
            else:
                time.sleep(2 ** attempt)
    
    articles = []
    for entry in feed.entries[:6]:  # Get top 6 articles
        # Clean description text
        description = entry.get('description', entry.get('summary', ''))
        # Remove HTML tags more thoroughly
        clean_description = re.sub(r'<[^>]+>', '', description)
        clean_description = re.sub(r'\s+', ' ', clean_description).strip()
        
        article = {
            'title': entry.get('title', 'No title'),
            'link': entry.get('link', ''),
            'description': clean_description[:1000],  # Limit description length
            'pubDate': entry.get('published', entry.get('pubDate', '')),
        }
        articles.append(article)
    
    print(f"✓ Found {len(articles)} articles")
    return articles

def generate_summary(client: OpenAI, article: Dict, attempt_num: int = 1) -> List[str]:
    """Generate AI summary for an article with retry logic"""
    print(f"\n→ Generating summary for: {article['title'][:60]}...")
    
    # More concise prompt for better results
    prompt = f"""Create 3-4 bullet point summary of this Boston news:

Title: {article['title']}
Content: {article['description'][:600]}

Return ONLY a JSON array of 3-4 bullet point strings, each under 25 words.
Example: ["First key point here", "Second key point here", "Third key point here"]"""

    # Try up to 3 times with exponential backoff
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"  API call attempt {attempt + 1}/{max_attempts}")
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a news summarizer. Return only valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=250,
                temperature=0.5,  # Lower temperature for more consistent output
                timeout=20
            )
            
            summary_text = response.choices[0].message.content.strip()
            
            # Clean up common JSON formatting issues
            summary_text = summary_text.replace('```json', '').replace('```', '').strip()
            
            # Try to parse as JSON
            try:
                summary_points = json.loads(summary_text)
                if isinstance(summary_points, list) and len(summary_points) >= 2:
                    print(f"  ✓ Generated {len(summary_points)} bullet points")
                    return summary_points[:4]  # Max 4 points
            except json.JSONDecodeError as je:
                print(f"  JSON parse error: {je}")
                # Try to extract bullet points from text
                lines = re.findall(r'"([^"]+)"', summary_text)
                if lines and len(lines) >= 2:
                    print(f"  ✓ Extracted {len(lines)} points from malformed JSON")
                    return lines[:4]
            
            # If we got here, the response wasn't usable
            print(f"  Invalid response format: {summary_text[:100]}...")
            
        except Exception as e:
            print(f"  ✗ Attempt {attempt + 1}/{max_attempts} failed: {str(e)[:100]}")
            if "rate_limit" in str(e).lower():
                sleep_time = 10 * (attempt + 1)  # Longer wait for rate limits
                print(f"  Rate limited, waiting {sleep_time} seconds...")
                time.sleep(sleep_time)
            elif attempt < max_attempts - 1:
                sleep_time = 2 ** attempt
                print(f"  Waiting {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
    
    # Fallback summary with more information
    print("  ⚠ Using fallback summary")
    title_preview = article['title'][:60]
    if len(article['title']) > 60:
        title_preview += "..."
    
    return [
        f"Breaking: {title_preview}",
        "Story details are being processed - check back soon for AI summary",
        "Click below for the full story from Boston.com"
    ]

def main():
    print("=" * 60)
    print("Boston News Summarizer - Starting")
    print("=" * 60)
    
    # Validate API key
    api_key = validate_api_key()
    if not api_key:
        # Create minimal output file so the website still works
        fallback_data = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {
                'total_articles': 0,
                'successful_summaries': 0,
                'generation_time': datetime.now().isoformat(),
                'error': 'API key not configured'
            }
        }
        with open('news-data.json', 'w', encoding='utf-8') as f:
            json.dump(fallback_data, f, indent=2)
        print("\nCreated fallback news-data.json file")
        exit(1)
    
    # Initialize OpenAI client
    try:
        client = OpenAI(
            api_key=api_key,
            timeout=30.0
        )
    except Exception as e:
        print(f"ERROR: Failed to initialize OpenAI client: {e}")
        exit(1)
    
    # Test API connection
    if not test_openai_connection(client):
        print("\n⚠ WARNING: OpenAI API test failed, but continuing anyway...")
    
    # RSS feed URL
    rss_url = "https://www.boston.com/feed/bdc-msn-rss"
    
    try:
        # Fetch articles
        articles = fetch_rss_feed(rss_url)
        
        if not articles:
            print("\nERROR: No articles found in RSS feed")
            # Create output with error message
            output_data = {
                'lastUpdated': datetime.now().isoformat(),
                'articles': [],
                'stats': {
                    'total_articles': 0,
                    'successful_summaries': 0,
                    'generation_time': datetime.now().isoformat(),
                    'error': 'No articles in RSS feed'
                }
            }
            with open('news-data.json', 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2)
            exit(1)
        
        # Generate summaries
        print(f"\n{'=' * 60}")
        print(f"Processing {len(articles)} articles...")
        print(f"{'=' * 60}")
        
        processed_articles = []
        successful_summaries = 0
        failed_summaries = 0
        
        for i, article in enumerate(articles):
            print(f"\n[Article {i+1}/{len(articles)}]")
            
            summary = generate_summary(client, article, i + 1)
            
            # Check if this was a successful AI-generated summary
            if not any("being processed" in point or "temporarily unavailable" in point for point in summary):
                successful_summaries += 1
            else:
                failed_summaries += 1
            
            processed_article = {
                'title': article['title'],
                'link': article['link'],
                'pubDate': article['pubDate'],
                'summary': summary
            }
            
            processed_articles.append(processed_article)
            
            # Rate limiting - wait between API calls
            if i < len(articles) - 1 and successful_summaries > 0:
                wait_time = 1.5  # Reduced wait time if things are working
                print(f"  Waiting {wait_time}s before next article...")
                time.sleep(wait_time)
        
        # Create output data
        output_data = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed_articles,
            'stats': {
                'total_articles': len(processed_articles),
                'successful_summaries': successful_summaries,
                'failed_summaries': failed_summaries,
                'generation_time': datetime.now().isoformat(),
                'success_rate': f"{(successful_summaries/len(processed_articles)*100):.1f}%" if processed_articles else "0%"
            }
        }
        
        # Write to JSON file
        with open('news-data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'=' * 60}")
        print(f"SUMMARY GENERATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"✓ Total articles processed: {len(processed_articles)}")
        print(f"✓ Successful AI summaries: {successful_summaries}")
        print(f"✗ Fallback summaries: {failed_summaries}")
        print(f"→ Success rate: {output_data['stats']['success_rate']}")
        print(f"→ Output saved to: news-data.json")
        print(f"{'=' * 60}\n")
        
        # Exit with error if all summaries failed (helps debug in GitHub Actions)
        if successful_summaries == 0 and len(processed_articles) > 0:
            print("WARNING: All AI summaries failed! Check your API key and quota.")
            print("The website will still work with fallback summaries.")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Create minimal output so website doesn't break
        emergency_data = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': [],
            'stats': {
                'total_articles': 0,
                'successful_summaries': 0,
                'generation_time': datetime.now().isoformat(),
                'error': str(e)
            }
        }
        with open('news-data.json', 'w', encoding='utf-8') as f:
            json.dump(emergency_data, f, indent=2)
        exit(1)

if __name__ == "__main__":
    main()
