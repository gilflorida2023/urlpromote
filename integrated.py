import requests
from bs4 import BeautifulSoup
import ollama
import sys
import sqlite3
from pathlib import Path
import csv
import re

import time

def format_duration(seconds):
    """
    Formats a duration in seconds into a human-readable string with appropriate units.
    - Sub-second durations: Shows three decimal places (e.g., "0.500s")
    - Whole seconds: Shows just seconds (e.g., "5s")
    - Minutes and up: Shows all relevant units, space-separated (e.g., "2m 30s", "1h 30m 45s")
    - Supports up to weeks for long-running operations
    """
    # Break down the duration into components
    weeks = int(seconds // (7 * 24 * 60 * 60))
    days = int((seconds % (7 * 24 * 60 * 60)) // (24 * 60 * 60))
    hours = int((seconds % (24 * 60 * 60)) // (60 * 60))
    minutes = int((seconds % (60 * 60)) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))

    def format_seconds(secs, ms):
        if secs == 0 and ms > 0:
            return f"0.{ms:03d}s"
        elif ms == 0:
            return f"{secs}s"
        else:
            return f"{secs}.{ms:03d}s"

    # Build the output according to the most significant non-zero unit
    parts = []
    if weeks > 0:
        parts.append(f"{weeks}w")
        parts.append(f"{days}d")
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif days > 0:
        parts.append(f"{days}d")
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif hours > 0:
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        parts.append(format_seconds(secs, milliseconds))
    elif minutes > 0:
        parts.append(f"{minutes}m")
        if secs > 0 or milliseconds > 0:
            parts.append(format_seconds(secs, milliseconds))
    else:
        parts.append(format_seconds(secs, milliseconds))
    return " ".join(parts)

def measure_elapsed_time(func, *args, **kwargs):
    """
    Measures the elapsed time of a function and returns a formatted string.
    Usage:
        def my_function(): ...
        elapsed = measure_elapsed_time(my_function)
        print(elapsed)
    Or with arguments:
        elapsed = measure_elapsed_time(some_func, arg1, arg2)
    """
    start = time.perf_counter()
    func(*args, **kwargs)
    end = time.perf_counter()
    duration = end - start
    return format_duration(duration)

## Example usage:
#if __name__ == "__main__":
#    import time
#
#    def test_sleep():
#        time.sleep(1.5)
#
#    print(measure_elapsed_time(test_sleep))  # e.g. "1.500s"
#
#    def long_sleep():
#        time.sleep(125)
#
#    print(measure_elapsed_time(long_sleep))  # e.g. "2m 5s"
#
#    def week_sleep():
#        time.sleep(0.01)  # simulate, don't actually sleep a week!
#    # You can mock/replace time.perf_counter for actual tests
#
#

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

def generate_promotion(url, content):
    prompt = (
        f"Generate exactly one complete, concise sentence (20-40 words, under 280 characters) summarizing the main point of the article at {url}. "
        f"Content: {content[:1500]}"
    )
    try:
        #response = ollama.generate(model='llama3.2', prompt=prompt, options={'num_predict': 50, 'temperature': 0.5, 'top_k': 1})
        response = ollama.generate(model='deepseek-r1:8b', prompt=prompt, options={'num_predict': 50, 'temperature': 0.5, 'top_k': 1})
        promotion = response['response'].strip()
        if len(promotion) > 280:
            promotion = promotion[:277] + "..."
        return promotion
    except Exception as e:
        return f"Error generating tagline: {e}"

def determine_promotion(url):
    content = fetch_webpage_content(url)
    promotion = generate_promotion(url, content)
    if promotion.startswith("Error"):
        promotion= "Error"
    return promotion

#def main():
#    if len(sys.argv) != 2:
#        print("Usage: python urltag.py <url>")
#        sys.exit(1)
#    
#    url = sys.argv[1]
#    content = fetch_webpage_content(url)
#    if content.startswith("Error"):
#        print(content)
#        sys.exit(1)
#    
#    tagline = generate_tagline(url, content)
#    if tagline.startswith("Error"):
#        print(tagline)
#        sys.exit(1)
#    
#    print(tagline)
#
#if __name__ == "__main__":
#    main()

def get_search_folders(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT n.node_id, n.title, COUNT(sfi.item_id)
    FROM node n
    LEFT JOIN search_folder_items sfi ON n.node_id = sfi.node_id
    WHERE n.type = 'vfolder' AND n.title LIKE '%Search%'
    GROUP BY n.node_id
    ORDER BY n.title
    """)
    
    folders = []
    for row in cursor.fetchall():
        folders.append({
            'id': row[0],
            'title': row[1],
            'count': row[2]
        })
    
    conn.close()
    return folders

def get_article_urls(folder_id, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # First inspect the items table structure
    cursor.execute("PRAGMA table_info(items)")
    columns = [col[1] for col in cursor.fetchall()]
    print("Items table columns:", ", ".join(columns))
    
    # Try different possible URL column names
    url_columns = ['url', 'source', 'link', 'guid']
    found_column = None
    
    for col in url_columns:
        if col in columns:
            found_column = col
            break
    
    if not found_column:
        print("Error: Could not find URL column in items table")
        return []
    
    print(f"Using column '{found_column}' for URLs")
    
    # Get actual article URLs from items table
    cursor.execute(f"""
    SELECT i.{found_column}
    FROM search_folder_items sfi
    JOIN items i ON sfi.item_id = i.item_id
    WHERE sfi.node_id = ?
    ORDER BY i.updated DESC
    """, (folder_id,))
    
    urls = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return urls

def export_urls_to_csv(folder_title, urls):
    # Replace spaces and special characters with underscores
    safe_title = re.sub(r'[^\w]', '_', folder_title)
    # Remove consecutive underscores
    safe_title = re.sub(r'_+', '_', safe_title)
    # Remove leading/trailing underscores
    safe_title = safe_title.strip('_')
    filename = f"liferea_urls_{safe_title}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
        writer.writerow(['Promotion','URL'])
        for url in urls:
            print(f"Trying {url}")
            promotion = determine_promotion(url)
            if promotion.startswith("Error"):
                continue
            writer.writerow([promotion, url])
            csvfile.flush()  # Force write to disk immediately
    
    print(f"\nExported {len(urls)} URLs to {filename}")
    print("Format: \"Article URL\"")

def main():
    db_path = str(Path("~/.local/share/liferea/liferea.db").expanduser())
    
    print("Liferea URL Exporter")
    print("=" * 50)
    
    folders = get_search_folders(db_path)
    if not folders:
        print("No search folders found!")
        return
    
    print("\nAvailable Search Folders:")
    for i, folder in enumerate(folders, 1):
        print(f"{i}. {folder['title']} ({folder['count']} items) [ID: {folder['id']}]")
    
    while True:
        selection = input("\nEnter folder number to export (q to quit): ").strip().lower()
        if selection == 'q':
            break
            
        if selection.isdigit() and 0 < int(selection) <= len(folders):
            folder = folders[int(selection)-1]
            print(f"\nExporting URLs from: {folder['title']}")
            
            urls = get_article_urls(folder['id'], db_path)
            if not urls:
                print("No URLs found in this folder")
                continue
                
            export_urls_to_csv(folder['title'], urls)
            print("\nOperation complete. You can:")
            print("1. Export another folder")
            print("2. Press 'q' to quit")
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    main()
