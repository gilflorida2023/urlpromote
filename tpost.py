#!/usr/bin/env python3
import csv
import sys
import os
import platform
import re
from subprocess import run, PIPE, CalledProcessError

class Clipboard:
    """Handles clipboard operations with pyclip-0.7.0"""
    @staticmethod
    def copy(text):
        try:
            import pyclip
            pyclip.copy(text)
            return True
        except (ImportError, Exception) as e:
            print(f"Clipboard error: {str(e)}")
            print("Text to paste manually:")
            print(text)
            return False

def validate_promotion(promotion, max_length=257):
    """Ensure promotion meets Twitter length requirements"""
    clean_text = re.sub(r'https?://\S+', '', promotion)
    return len(clean_text) <= max_length

def process_csv(csv_file, max_length=257):
    """Main function to process CSV and prepare tweets"""
    if not os.path.exists(csv_file):
        print(f"Error: File '{csv_file}' not found")
        return

    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header row
        
        for row_num, row in enumerate(reader, 1):
            if len(row) < 2:
                print(f"Skipping row {row_num}: Insufficient columns")
                continue

            promotion, url = row[0].strip(), row[1].strip()
            
            # Validate length
            if not validate_promotion(promotion, max_length):
                print(f"\n⚠️ Skipping row {row_num} (Exceeds {max_length} chars)")
                print(f"Promotion: {promotion[:50]}...")
                continue

            # Format for Twitter
            tweet_text = f"{promotion}\n{url}"
            print(f"\n✅ Row {row_num} ready for Twitter:")
            print("="*40)
            print(tweet_text)
            print("="*40)
            print(f"Chars: {len(promotion)} (max {max_length}) + URL: {len(url)}")

            # Copy to clipboard
            if not Clipboard.copy(tweet_text):
                print("\n⚠️ Could not copy to clipboard - please copy manually above")

            # Wait for user
            while True:
                action = input("\n[Enter] Next  [s] Skip  [q] Quit: ").strip().lower()
                if action == 'q':
                    print("\n🏁 Finished posting!")
                    return
                elif action == 's':
                    print("Skipping...")
                    break
                elif not action:
                    break  # Continue to next item

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python twitter_poster.py your_file.csv [max_promotion_length]")
        print("Default max length: 257 (280 with URL)")
        sys.exit(1)

    max_len = int(sys.argv[2]) if len(sys.argv) > 2 else 257
    process_csv(sys.argv[1], max_len)
