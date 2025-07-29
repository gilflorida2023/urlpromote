#!/usr/bin/env python3
import sqlite3
import csv
import sys
from pathlib import Path

def get_folder_name_from_filename(filename):
    """Extract folder name from filename like 'liferea_urls_gaza_Saved_Search.csv'"""
    if not filename.startswith('liferea_urls_') or not filename.endswith('.csv'):
        raise ValueError("Filename must be in format 'liferea_urls_<foldername>.csv'")
    return filename[len('liferea_urls_'):-len('.csv')]

def create_integration_table(conn):
    """Create the integration table if it doesn't exist"""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS integration (
        promotion TEXT,
        url TEXT,
        folder_name TEXT,
        UNIQUE(url, folder_name)  -- Ensure no duplicate URLs per folder
    )
    """)
    conn.commit()

def import_csv_to_table(csv_filename, db_path):
    """Import all CSV data into the integration table"""
    folder_name = get_folder_name_from_filename(Path(csv_filename).name)
    
    conn = sqlite3.connect(db_path)
    create_integration_table(conn)
    cursor = conn.cursor()
    
    # First count rows in CSV (excluding header)
    with open(csv_filename, 'r', encoding='utf-8') as csvfile:
        csv_reader = csv.reader(csvfile)
        next(csv_reader)  # Skip header
        csv_rows = list(csv_reader)
    
    if not csv_rows:
        print("CSV file contains no data rows (only header)")
        return
    
    print(f"Found {len(csv_rows)} records in CSV file")
    
    # Prepare data for batch insert
    data_to_insert = []
    for row in csv_rows:
        if len(row) >= 2:  # Ensure we have at least promotion and URL
            promotion = row[0]
            url = row[1]
            data_to_insert.append((promotion, url, folder_name))
    
    # Clear existing data for this folder
    cursor.execute("DELETE FROM integration WHERE folder_name = ?", (folder_name,))
    
    # Insert all rows in a single transaction
    cursor.executemany(
        "INSERT INTO integration (promotion, url, folder_name) VALUES (?, ?, ?)",
        data_to_insert
    )
    
    conn.commit()
    print(f"Successfully imported {cursor.rowcount} records to integration table")
    conn.close()

def main():
    if len(sys.argv) != 2:
        print("Usage: dbtestread.py <csv_filename>")
        sys.exit(1)
    
    csv_filename = sys.argv[1]
    db_path = str(Path("~/.local/share/liferea/liferea.db").expanduser())
    
    try:
        import_csv_to_table(csv_filename, db_path)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
