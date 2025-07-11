import requests
from bs4 import BeautifulSoup
import ollama
import sys

def fetch_webpage_content(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove irrelevant sections
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        # Try to find article content
        article = soup.find('article') or soup.find('div', class_=['article-text', 'content'])
        text = article.get_text(strip=True) if article else soup.get_text(strip=True)
        return text[:2000]  # Limit to avoid overwhelming Ollama
    except requests.RequestException as e:
        return f"Error fetching URL: {e}"

def generate_tagline(url, content):
    prompt = (
        f"Generate exactly one complete, concise sentence (20-40 words, under 280 characters) summarizing the main point of the article at {url}. "
        f"Content: {content[:1500]}"
    )
    try:
        response = ollama.generate(model='llama3.2', prompt=prompt, options={'num_predict': 50, 'temperature': 0.5, 'top_k': 1})
        tagline = response['response'].strip()
        if len(tagline) > 280:
            tagline = tagline[:277] + "..."
        return tagline
    except Exception as e:
        return f"Error generating tagline: {e}"

def main():
    if len(sys.argv) != 2:
        print("Usage: python urltag.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]
    content = fetch_webpage_content(url)
    if content.startswith("Error"):
        print(content)
        sys.exit(1)
    
    tagline = generate_tagline(url, content)
    if tagline.startswith("Error"):
        print(tagline)
        sys.exit(1)
    
    print(tagline)

if __name__ == "__main__":
    main()
