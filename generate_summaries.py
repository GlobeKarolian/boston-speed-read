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

# Initialize OpenAI client with the new v1+ syntax
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch and parse RSS feed"""
    print(f"Fetching RSS feed from {url}")
    feed = feedparser.parse(url)
    
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
    """Generate AI summary for an article"""
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

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        summary_text = response.choices[0].message.content.strip()
        
        # Try to parse as JSON first
        try:
            summary_points = json.loads(summary_text)
            if isinstance(summary_points, list):
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
        
        return summary_points[:4]  # Limit to 4 points
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        return [
            "Unable to generate AI summary for this article",
            "Please click 'Read Full Story' for complete details",
            "Summary generation will be retried on next update"
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
        
        # Generate summaries
        processed_articles = []
        for i, article in enumerate(articles):
            print(f"Processing article {i+1}/{len(articles)}")
            
            summary = generate_summary(article)
            
            processed_article = {
                'title': article['title'],
                'link': article['link'],
                'pubDate': article['pubDate'],
                'summary': summary
            }
            
            processed_articles.append(processed_article)
            
            # Rate limiting - wait 1 second between API calls
            if i < len(articles) - 1:
                time.sleep(1)
        
        # Create output data
        output_data = {
            'lastUpdated': datetime.now().isoformat(),
            'articles': processed_articles
        }
        
        # Write to JSON file
        with open('news-data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"Successfully generated summaries for {len(processed_articles)} articles")
        print("Output saved to news-data.json")
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
