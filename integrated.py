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
import threading
import unicodedata
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

class OllamaWorkerPool:
    def __init__(self, hosts):
        self.hosts = hosts
        self.task_queue = Queue()
        self.result_queue = Queue()
        self.workers = []
        self.shutdown_flag = False
        
    def start(self):
        """Start worker threads"""
        for host in self.hosts:
            worker = threading.Thread(
                target=self._worker_loop,
                args=(host,),
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
    
    def _worker_loop(self, host):
        """Worker thread processing loop"""
        while not self.shutdown_flag:
            try:
                task = self.task_queue.get(timeout=1)
                if task is None:  # Sentinel value for shutdown
                    break
                    
                url, callback = task
                try:
                    result = self._process_url(host, url)
                    self.result_queue.put((url, result))
                    if callback:
                        callback(url, result)
                except Exception as e:
                    print(f"Worker error on {host}: {str(e)}")
                finally:
                    self.task_queue.task_done()
            except:
                continue
    
    def _process_url(self, host, url):
        """Process a single URL using the specified host"""
        try:
            start_time = time.time()
            result = subprocess.run(
                ["./article3.sh", host, url],
                capture_output=True,
                text=True,
                check=True,
                env={'TERM': 'dumb', **os.environ}
            )
            processing_time = time.time() - start_time
            if processing_time > 30:  # Log slow processing
                print(f"  [i] Processed in {processing_time:.1f}s: {url[:60]}...")
            promotion = clean_text(result.stdout.strip())
            return promotion if promotion and "Error" not in promotion else "Error"
        except subprocess.CalledProcessError as e:
            print(f"  [!] Process error on {host}: {clean_text(e.stderr.strip())[:200]}...")
            return "Error"
        except Exception as e:
            print(f"  [!] System error on {host}: {str(e)}")
            return "Error"
    
    def add_task(self, url, callback=None):
        """Add a URL processing task to the queue"""
        self.task_queue.put((url, callback))
    
    def shutdown(self):
        """Gracefully shutdown the worker pool"""
        self.shutdown_flag = True
        for _ in self.workers:
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join(timeout=5)

def determine_promotion(url, worker_pool):
    """Generate promotion using worker pool without timeouts"""
    result_queue = Queue()
    
    def callback(url, result):
        result_queue.put((url, result))
    
    worker_pool.add_task(url, callback)
    
    try:
        _, result = result_queue.get()  # No timeout
        return result
    except Exception as e:
        print(f"  [!] Queue error: {str(e)}")
        return f"Error: {str(e)}"

def stop_liferea():
    """Gracefully stop Liferea process if running"""
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == 'liferea':
                print("Stopping Liferea process...")
                proc.terminate()
                try:
                    proc.wait(5)
                except psutil.TimeoutExpired:
                    proc.kill()
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

def clean_text(text):
    """Remove control characters and normalize to ASCII"""
    if not text:
        return ""
    text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    text = text.replace('"', "'").strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def normalize_url(url):
    """Normalize URL for better deduplication"""
    if not url:
        return url
    url = re.sub(r'[?&](utm_[^&]+|fbclid|gclid|mc_[^&]+)=[^&]*', '', url)
    url = re.sub(r'[?&]sid=[^&]*', '', url)
    url = re.sub(r'/#.*$', '', url)
    url = re.sub(r'^http://', 'https://', url)
    url = re.sub(r'^https://www\.', 'https://', url)
    url = re.sub(r'/\?$', '', url)
    url = re.sub(r'/$', '', url)
    url = re.sub(r'\?$', '', url)
    return url.lower().strip()

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
    """Retrieve article URLs from a specific folder"""
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
    
    seen_urls = set()
    urls = []
    for row in cursor.fetchall():
        url = row[0]
        if url:
            normalized = normalize_url(url)
            if normalized and normalized not in seen_urls:
                seen_urls.add(normalized)
                urls.append(url)
    conn.close()
    return urls

def load_processed_urls(filename):
    """Load already processed URLs from existing CSV"""
    processed_urls = set()
    try:
        with open(filename, 'r', encoding='ascii') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            for row in reader:
                if len(row) >= 2:
                    processed_urls.add(normalize_url(row[1]))
    except FileNotFoundError:
        pass
    return processed_urls

def export_urls_to_csv(folder_title, urls, worker_pool):
    """Export URLs with promotions to CSV"""
    safe_title = re.sub(r'[^\w]', '_', folder_title)
    safe_title = re.sub(r'_+', '_', safe_title).strip('_')
    filename = f"liferea_urls_{safe_title}.csv"

    processed_urls = load_processed_urls(filename)
    new_urls_count = 0

    with open(filename, 'a', newline='', encoding='ascii') as csvfile:
        writer = csv.writer(csvfile,
                          quoting=csv.QUOTE_ALL,
                          delimiter=',',
                          escapechar='\\',
                          doublequote=False)
        
        if csvfile.tell() == 0:
            writer.writerow(['Promotion', 'URL'])

        with ThreadPoolExecutor(max_workers=len(worker_pool.hosts)) as executor:
            future_to_url = {
                executor.submit(
                    lambda u: (u, determine_promotion(u, worker_pool)),
                    url
                ): url 
                for url in urls 
                if normalize_url(url) not in processed_urls
            }

            for future in as_completed(future_to_url):
                url, promotion = future.result()
                normalized = normalize_url(url)
                
                if not normalized:
                    continue

                if promotion == "Error":
                    print(f"  [!] Failed to generate promotion for: {url[:80]}...")
                    processed_urls.add(normalized)
                    continue

                clean_url = clean_text(url)
                
                if promotion.startswith("Reject:"):
                    print(f"  [!] Skipping rejected promotion: {promotion[:80]}...")
                    processed_urls.add(normalized)
                    continue
                    
                print(f"  [+] Generated promotion for: {url[:60]}...")
                writer.writerow([promotion, clean_url])
                csvfile.flush()
                processed_urls.add(normalized)
                new_urls_count += 1

    print(f"\nOperation complete. Processed {new_urls_count} new URLs out of {len(urls)} total.")
    print(f"Results saved to {filename}")

def main():
    if len(sys.argv) < 2:
        print("Usage: ./integrated.py <ollama_host1> [<ollama_host2> ...]")
        sys.exit(1)
    
    ollama_hosts = sys.argv[1:]
    print(f"Using Ollama hosts: {', '.join(ollama_hosts)}")
    
    worker_pool = OllamaWorkerPool(ollama_hosts)
    worker_pool.start()
    
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
                export_urls_to_csv(folder['title'], urls, worker_pool)
                print("\nOperation complete. You can:")
                print("1. Export another folder")
                print("2. Press 'q' to quit")
            else:
                print("Invalid selection. Please try again.")
    
    finally:
        if was_running:
            start_liferea()
        worker_pool.shutdown()

if __name__ == "__main__":
    main()
