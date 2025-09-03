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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Initialize OpenAI client with timeout settings
client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    timeout=60.0  # 60 second timeout
)

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
    print(f"Fetching RSS feed from {url}")
    
    session = create_session_with_retries()
    
    for attempt in range(3):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1}/3 failed to fetch RSS: {e}")
            if attempt == 2:
                # Fallback to feedparser direct parsing
                feed = feedparser.parse(url)
            else:
                time.sleep(2 ** attempt)
    
    articles = []
    for entry in feed.entries[:6]:  # Get top 6 articles
        # Clean description text
        description = entry.get('description', '')
        # Remove HTML tags
        clean_description = re.sub(r'<[^>]+>', '', description).strip()
        
        article = {
            'title': entry.get('title', 'No title'),
            'link': entry.get('link', ''),
            'description': clean_description,
            'pubDate': entry.get('published', ''),
        }
        articles.append(article)
    
    print(f"Found {len(articles)} articles")
    return articles

def generate_summary(article: Dict) -> List[str]:
    """Generate AI summary for an article with retry logic"""
    print(f"Generating summary for: {article['title'][:60]}...")
    
    prompt = f"""Please create a concise 3-4 bullet point summary of this Boston news article:

Title: {article['title']}

Article excerpt: {article['description'][:800]}

Instructions:
- Create exactly 3-4 bullet points
- Each bullet should be a complete, informative sentence
- Focus on the key facts: who, what, when, where, why
- Keep each bullet under 25 words
- Use clear, engaging language
- Return ONLY the bullet points as a JSON array of strings
- Do not include any markdown or HTML formatting"""

    # Try up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            print(f"  API call attempt {attempt + 1}/3")
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7,
                timeout=30  # 30 second timeout per request
            )
            
            summary_text = response.choices[0].message.content.strip()
            
            # Try to parse as JSON first
            try:
                summary_points = json.loads(summary_text)
                if isinstance(summary_points, list):
                    print(f"  Successfully generated {len(summary_points)} bullet points")
                    return summary_points
            except json.JSONDecodeError:
                pass
            
            # Fallback: parse as plain text
            lines = [line.strip() for line in summary_text.split('\n') if line.strip()]
            summary_points = []
            
            for line in lines:
                # Remove bullet point markers
                clean_line = re.sub(r'^[•\-\*\d+\.]\s*', '', line).strip()
                if clean_line and len(clean_line) > 10:
                    summary_points.append(clean_line)
            
            if summary_points:
                print(f"  Successfully parsed {len(summary_points)} bullet points from text")
                return summary_points[:4]  # Limit to 4 points
            
        except Exception as e:
            print(f"  Attempt {attempt + 1}/3 failed: {str(e)}")
            if attempt < 2:  # Don't sleep on the last attempt
                sleep_time = (2 ** attempt) + 1  # 1, 3, 7 seconds
                print(f"  Waiting {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
    
    # If all attempts failed, return fallback summary
    print("  All attempts failed, using fallback summary")
    return [
        f"Boston news story: {article['title'][:60]}{'...' if len(article['title']) > 60 else ''}",
        "AI summary generation temporarily unavailable due to connectivity issues",
        "Click 'Read Full Story' below for complete article details",
        "Summary generation will be retried on next scheduled update"
    ]

def main():
    print("Starting Boston News Summarizer...")
    
    # Check if API key is available
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        exit(1)
    
    # RSS feed URL
    rss_url = "https://www.boston.com/feed/bdc-msn-rss"
    
    try:
        # Fetch articles
        articles = fetch_rss_feed(rss_url)
        
        if not articles:
            print("ERROR: No articles found in RSS feed")
            exit(1)
        
        # Generate summaries
        processed_articles = []
        successful_summaries = 0
        
        for i, article in enumerate(articles):
            print(f"\nProcessing article {i+1}/{len(articles)}")
            
            summary = generate_summary(article)
            
            # Check if this was a successful AI-generated summary
            if not any("AI summary generation temporarily unavailable" in point for point in summary):
                successful_summaries += 1
            
            processed_article = {
                'title': article['title'],
                'link': article['link'],
                'pubDate': article['pubDate'],
                'summary': summary
            }
            
            processed_articles.append(processed_article)
            
            # Rate limiting - wait between API calls
            if i < len(articles) - 1:
                print(f"  Waiting 2 seconds before next article...")
                time.sleep(2)
        
        # Create output data
        output_data = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed_articles,
            'stats': {
                'total_articles': len(processed_articles),
                'successful_summaries': successful_summaries,
                'generation_time': datetime.now().isoformat()
            }
        }
        
        # Write to JSON file
        with open('news-data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\nSUCCESS:")
        print(f"- Generated summaries for {len(processed_articles)} articles")
        print(f"- {successful_summaries} AI-generated summaries")
        print(f"- {len(processed_articles) - successful_summaries} fallback summaries")
        print(f"- Output saved to news-data.json")
        
        # Exit with success even if some summaries failed
        # The website will still work with fallback summaries
        
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)

if __name__ == "__main__":
    main()
