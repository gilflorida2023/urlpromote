#!/usr/bin/env python3
import os
import sys
import sqlite3
from pathlib import Path
import csv
import re
import subprocess
import time
import psutil
import unicodedata

def stop_liferea():
    """Gracefully stop Liferea process if running"""
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == 'liferea':
                print("Stopping Liferea process...")
                proc.terminate()  # Try to terminate gracefully
                try:
                    proc.wait(5)  # Wait up to 5 seconds
                except psutil.TimeoutExpired:
                    proc.kill()   # Force kill if not responding
                return True
        return False
    except Exception as e:
        print(f"Warning: Could not stop Liferea - {str(e)}")
        return False

def start_liferea():
    """Start Liferea process"""
    try:
        print("Restarting Liferea...")
        subprocess.Popen(['liferea'], start_new_session=True)
        return True
    except Exception as e:
        print(f"Warning: Could not start Liferea - {str(e)}")
        return False

def format_duration(seconds):
    """
    Formats a duration in seconds into a human-readable string.
    Examples: "0.500s", "5s", "2m 30s", "1h 30m 45s"
    """
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
    """Measures and formats the execution time of a function"""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    end = time.perf_counter()
    duration = end - start
    return result, format_duration(duration)

def clean_text(text):
    """Remove control characters and normalize to ASCII"""
    if not text:
        return ""
    
    # Remove ANSI escape sequences
    text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
    
    # Normalize Unicode to ASCII
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Remove remaining control chars
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    
    # Standardize quotes and whitespace
    text = text.replace('"', "'").strip()
    text = re.sub(r'\s+', ' ', text)
    
    return text

def normalize_url(url):
    """Normalize URL for better deduplication"""
    if not url:
        return url
    
    # Remove common tracking parameters and fragments
    url = re.sub(r'[?&](utm_[^&]+|fbclid|gclid|mc_[^&]+)=[^&]*', '', url)
    url = re.sub(r'[?&]sid=[^&]*', '', url)
    url = re.sub(r'/#.*$', '', url)
    
    # Standardize protocol and www
    url = re.sub(r'^http://', 'https://', url)
    url = re.sub(r'^https://www\.', 'https://', url)
    
    # Remove trailing slashes and empty query strings
    url = re.sub(r'/\?$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'\?$', '', url)
    
    return url.lower().strip()

def determine_promotion(url):
    """Generate promotion using article2.sh script with clean output"""
    try:
        result = subprocess.run(
            ["./article2.sh", url],
            capture_output=True,
            text=True,
            check=True,
            env={'TERM': 'dumb', **os.environ}  # Prevent control characters
        )
        promotion = clean_text(result.stdout.strip())
        
        if not promotion or "Error" in promotion:
            return "Error"
            
        return promotion
    except subprocess.CalledProcessError as e:
        print(f"Error generating promotion: {clean_text(e.stderr.strip())}")
        return "Error"
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return "Error"

def get_search_folders(db_path):
    """Retrieve search folders from Liferea database"""
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
    """Retrieve article URLs from a specific folder with deduplication"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(items)")
    columns = [col[1] for col in cursor.fetchall()]
    
    url_columns = ['url', 'source', 'link', 'guid']
    found_column = None
    
    for col in url_columns:
        if col in columns:
            found_column = col
            break
    
    if not found_column:
        print("Error: Could not find URL column in items table")
        return []
    
    cursor.execute(f"""
    SELECT i.{found_column}
    FROM search_folder_items sfi
    JOIN items i ON sfi.item_id = i.item_id
    WHERE sfi.node_id = ?
    ORDER BY i.updated DESC
    """, (folder_id,))
    
    # Use a set to track seen URLs while preserving order
    seen_urls = set()
    urls = []
    
    for row in cursor.fetchall():
        url = row[0]
        if url:
            normalized = normalize_url(url)
            if normalized and normalized not in seen_urls:
                seen_urls.add(normalized)
                urls.append(url)  # Store original URL
    
    conn.close()
    return urls

def load_processed_urls(filename):
    """Load already processed URLs from existing CSV"""
    processed_urls = set()
    try:
        with open(filename, 'r', encoding='ascii') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header
            for row in reader:
                if len(row) >= 2:
                    processed_urls.add(normalize_url(row[1]))
    except FileNotFoundError:
        pass
    return processed_urls

def export_urls_to_csv(folder_title, urls):
    """Export URLs with promotions to clean ASCII CSV"""
    safe_title = re.sub(r'[^\w]', '_', folder_title)
    safe_title = re.sub(r'_+', '_', safe_title).strip('_')
    filename = f"liferea_urls_{safe_title}.csv"

    # Track URLs we've already processed
    processed_urls = load_processed_urls(filename)
    new_urls_count = 0

    with open(filename, 'a', newline='', encoding='ascii') as csvfile:
        writer = csv.writer(csvfile,
                          quoting=csv.QUOTE_ALL,
                          delimiter=',',
                          escapechar='\\',
                          doublequote=False)
        
        # Write header only if file is new
        if csvfile.tell() == 0:
            writer.writerow(['Promotion', 'URL'])

        for i, url in enumerate(urls, 1):
            normalized = normalize_url(url)
            if not normalized:
                continue

            if normalized in processed_urls:
                print(f"\nSkipping already processed URL {i}/{len(urls)}: {clean_text(url)[:80]}...")
                continue

            print(f"\nProcessing URL {i}/{len(urls)}: {clean_text(url)[:80]}...")
            promotion, duration = measure_elapsed_time(determine_promotion, url)

            if promotion == "Error":
                print(f"  [!] Failed to generate promotion (took {duration})")
                processed_urls.add(normalized)  # Mark as processed to avoid retries
                continue

            clean_url = clean_text(url)
            
            if promotion.startswith("Reject:"):
                print(f"  [!] Skipping rejected promotion: {promotion[:80]}...")
                processed_urls.add(normalized)  # Mark as processed
                continue
                
            print(f"  [+] Generated promotion ({duration}): {promotion[:50]}...")
            writer.writerow([promotion, clean_url])
            csvfile.flush()
            processed_urls.add(normalized)
            new_urls_count += 1

    print(f"\nOperation complete. Processed {new_urls_count} new URLs out of {len(urls)} total.")
    print(f"Results saved to {filename}")

def main():
    # Stop Liferea before database operations
    was_running = stop_liferea()
    
    try:
        db_path = str(Path("~/.local/share/liferea/liferea.db").expanduser())
        
        print("\nLiferea URL Exporter")
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
                    
                print(f"Found {len(urls)} unique URLs after deduplication")
                export_urls_to_csv(folder['title'], urls)
                print("\nOperation complete. You can:")
                print("1. Export another folder")
                print("2. Press 'q' to quit")
            else:
                print("Invalid selection. Please try again.")
    
    finally:
        pass
        # Restart Liferea if it was running
        #if was_running:
            #start_liferea()

if __name__ == "__main__":
    main()
