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

def compare_csv_with_table(csv_filename, db_path):
    """Thoroughly compare all CSV contents with database table"""
    folder_name = get_folder_name_from_filename(Path(csv_filename).name)
    
    # Read all CSV data
    csv_data = []
    with open(csv_filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 2:
                # Normalize by stripping whitespace
                promotion = row[0].strip()
                url = row[1].strip()
                csv_data.append((promotion, url))
    
    if not csv_data:
        print("CSV file contains no data rows (only header)")
        return False
    
    print(f"CSV contains {len(csv_data)} records")
    
    # Read all matching database data
    db_data = []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT promotion, url FROM integration 
    WHERE folder_name = ?
    ORDER BY url
    """, (folder_name,))
    
    db_data = [(row[0].strip(), row[1].strip()) for row in cursor.fetchall()]
    conn.close()
    
    print(f"Database contains {len(db_data)} matching records")
    
    # Convert to sets for comparison
    csv_set = set(csv_data)
    db_set = set(db_data)
    
    # Check for missing records in either direction
    csv_only = csv_set - db_set
    db_only = db_set - csv_set
    
    if not csv_only and not db_only:
        print("Perfect match! All records identical.")
        return True
    
    # Report discrepancies
    if csv_only:
        print(f"\n{len(csv_only)} records found in CSV but not in database:")
        for i, record in enumerate(sorted(csv_only)[:5], 1):  # Show first 5 as sample
            print(f"  {i}. Promotion: {record[0][:50]}... | URL: {record[1][:50]}...")
        if len(csv_only) > 5:
            print(f"  ... and {len(csv_only)-5} more")
    
    if db_only:
        print(f"\n{len(db_only)} records found in database but not in CSV:")
        for i, record in enumerate(sorted(db_only)[:5], 1):  # Show first 5 as sample
            print(f"  {i}. Promotion: {record[0][:50]}... | URL: {record[1][:50]}...")
        if len(db_only) > 5:
            print(f"  ... and {len(db_only)-5} more")
    
    # Detailed count comparison
    print("\nSummary:")
    print(f"Total CSV records: {len(csv_data)}")
    print(f"Total DB records: {len(db_data)}")
    print(f"Matching records: {len(csv_set & db_set)}")
    
    return False

def main():
    if len(sys.argv) != 2:
        print("Usage: dbtestcompare.py <csv_filename>")
        sys.exit(1)
    
    csv_filename = sys.argv[1]
    db_path = str(Path("~/.local/share/liferea/liferea.db").expanduser())
    
    try:
        success = compare_csv_with_table(csv_filename, db_path)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
