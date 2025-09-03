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

def validate_api_key():
    """Validate OpenAI API key"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return None
    print(f"API key found: {api_key[:7]}...{api_key[-4:]}")
    return api_key

def fetch_rss_feed(url: str, count: int = 6) -> List[Dict]:
    """Fetch and parse RSS feed"""
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
            'description': clean_desc[:1500],  # Longer for better context
            'content': content[:2000] if content else clean_desc[:2000],
            'pubDate': entry.get('published', entry.get('pubDate', ''))
        }
        articles.append(article)
    
    print(f"✓ Found {len(articles)} articles")
    return articles

def generate_ai_summary(client: OpenAI, article: Dict) -> Optional[List[str]]:
    """Generate engaging AI summary with better prompts"""
    print(f"\nGenerating summary for: {article['title'][:60]}...")
    
    # Use more content for better summaries
    content = article['content'] if article['content'] else article['description']
    
    # Much better prompt for engaging summaries
    prompt = f"""You are a skilled Boston news journalist creating engaging, informative bullet-point summaries for busy readers.

Article Title: {article['title']}

Article Content: {content[:1200]}

Create exactly 3 compelling bullet points that:
1. First bullet: Capture the MAIN NEWS - what happened and why it matters to Boston residents
2. Second bullet: Provide KEY DETAILS - important facts, numbers, quotes, or context that readers need to know  
3. Third bullet: Explain the IMPACT or WHAT'S NEXT - how this affects the community or what happens next

Requirements:
- Make each bullet point 15-25 words, informative and engaging
- Use active voice and strong verbs
- Include specific details (names, numbers, dates, locations) when available
- Write for a local Boston audience who cares about their community
- Don't just repeat the headline - add NEW information and context
- Return ONLY a JSON array of 3 strings

Example format:
["Mayor Wu announces $50M investment in affordable housing, targeting 1,000 new units in Roxbury and Dorchester by 2026", "The initiative includes partnerships with local developers and prioritizes families earning below $75,000 annually", "Housing advocates praise the plan but say Boston needs 20,000 units to address the crisis"]"""

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
        
        # Clean and parse JSON
        content = content.replace('```json', '').replace('```', '').strip()
        
        try:
            points = json.loads(content)
            if isinstance(points, list) and len(points) == 3:
                print(f"  ✓ Generated engaging AI summary")
                return points
        except json.JSONDecodeError:
            # Try to extract bullet points from text
            lines = content.split('\n')
            points = []
            for line in lines:
                # Remove bullet markers and quotes
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
    title = article['title']
    content = article['content'] if article['content'] else article['description']
    
    # Extract key information
    sentences = re.split(r'[.!?]+', content)
    clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    summary = []
    
    # Try to make informative fallbacks
    if "Red Sox" in title or "Celtics" in title or "Patriots" in title or "Bruins" in title:
        summary.append(f"Boston sports update: {title[:70]}")
    elif any(word in title.lower() for word in ['mayor', 'city', 'council', 'police', 'fire']):
        summary.append(f"Local government news: {title[:70]}")
    else:
        summary.append(f"Breaking: {title[:70]}")
    
    # Add first substantial sentence if available
    if clean_sentences:
        summary.append(clean_sentences[0][:80])
    else:
        summary.append("Story developing with updates expected throughout the day")
    
    # Add curiosity gap as third bullet
    curiosity_gaps = [
        "The surprising detail that has Boston residents talking is revealed inside",
        "What happens next could affect thousands of Boston area families",
        "The unexpected reason behind this decision changes everything",
        "Local officials reveal the one thing nobody saw coming",
        "The real story involves a twist that even surprised investigators"
    ]
    import random
    summary.append(random.choice(curiosity_gaps))
    
    return summary

def main():
    print("=" * 60)
    print("Boston News Summarizer - Enhanced Version")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Validate API key
    api_key = validate_api_key()
    
    # Initialize OpenAI client if key exists
    client = None
    if api_key:
        try:
            client = OpenAI(api_key=api_key, timeout=30.0)
            # Quick test
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
    articles = fetch_rss_feed("https://www.boston.com/feed/bdc-msn-rss")
    
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
                    # Rate limiting
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
    
    # Save output
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
    print(f"→ Output saved to news-data.json")
    print(f"{'=' * 60}\n")
    
    # Exit successfully
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        print(f"Fatal error: {e}")
        # Create emergency output
        with open('news-data.json', 'w') as f:
            json.dump({
                'lastUpdated': datetime.now().isoformat(),
                'articles': [],
                'stats': {'error': str(e)}
            }, f, indent=2)
        exit(0)
