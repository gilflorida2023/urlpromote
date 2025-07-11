import sqlite3
from pathlib import Path
import csv
import re

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
        writer.writerow(['URL'])
        for url in urls:
            writer.writerow([url])
    
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
