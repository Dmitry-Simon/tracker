"""
Migration Helper: Add Spender Field to Existing Transactions

This script helps you bulk-update existing transactions in your database
by detecting spenders from card patterns in their descriptions.

WARNING: This will modify your database. Make sure you have a backup!
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import db
from src.parsers import TransactionParser

def migrate_existing_transactions(default_spender="Joint", dry_run=True):
    """
    Scans all existing transactions and adds the spender field based on:
    1. Card patterns in description
    2. Default spender if no pattern found
    
    Args:
        default_spender: Default value for transactions without card patterns
        dry_run: If True, only shows what would be changed without actually changing it
    """
    print("=== Spender Migration Helper ===\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE: Will show changes without modifying database\n")
    else:
        print("⚠️  LIVE MODE: Will actually modify the database!\n")
        confirm = input("Are you sure you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            return
    
    # Get all transactions (you may need to implement this in db.py)
    print("Fetching all transactions from database...\n")
    
    # For now, we'll use a workaround - get transactions from a large date range
    # You might want to add a get_all_transactions() method to db.py
    all_txs = db.get_transactions_by_range('2000-01-01', '2099-12-31')
    
    if not all_txs:
        print("No transactions found in database.")
        return
    
    print(f"Found {len(all_txs)} total transactions\n")
    
    # Create parser for spender detection
    parser = TransactionParser(default_spender=default_spender)
    
    # Track statistics
    stats = {
        'total': len(all_txs),
        'already_have_spender': 0,
        'pattern_detected': 0,
        'default_assigned': 0,
        'person_a': 0,
        'person_b': 0,
        'joint': 0
    }
    
    updates_to_make = []
    
    print("Processing transactions...\n")
    for tx in all_txs:
        tx_id = tx.get('_id')
        current_spender = tx.get('spender')
        description = tx.get('description', '')
        
        # Skip if already has spender
        if current_spender:
            stats['already_have_spender'] += 1
            continue
        
        # Detect spender
        new_spender = parser.detect_spender(description)
        
        # Track whether it was pattern-detected or default
        if any(card in description for card in parser.card_patterns.keys()):
            stats['pattern_detected'] += 1
        else:
            stats['default_assigned'] += 1
        
        # Track spender counts
        if new_spender == 'Person A':
            stats['person_a'] += 1
        elif new_spender == 'Person B':
            stats['person_b'] += 1
        else:
            stats['joint'] += 1
        
        # Store update
        updates_to_make.append({
            '_id': tx_id,
            'date': tx.get('date'),
            'amount': tx.get('amount'),
            'description': description[:60],
            'new_spender': new_spender
        })
    
    # Print statistics
    print("\n=== Migration Statistics ===")
    print(f"Total transactions: {stats['total']}")
    print(f"Already have spender: {stats['already_have_spender']}")
    print(f"Need to update: {len(updates_to_make)}")
    print(f"\nDetection method:")
    print(f"  Pattern detected: {stats['pattern_detected']}")
    print(f"  Default assigned: {stats['default_assigned']}")
    print(f"\nSpender distribution:")
    print(f"  Person A: {stats['person_a']}")
    print(f"  Person B: {stats['person_b']}")
    print(f"  Joint: {stats['joint']}")
    
    if not updates_to_make:
        print("\n✓ All transactions already have spender assigned!")
        return
    
    # Show sample updates
    print("\n=== Sample Updates (first 10) ===")
    for update in updates_to_make[:10]:
        print(f"\nDate: {update['date']}")
        print(f"Amount: {update['amount']}")
        print(f"Description: {update['description']}...")
        print(f"Will assign: {update['new_spender']}")
    
    if len(updates_to_make) > 10:
        print(f"\n... and {len(updates_to_make) - 10} more")
    
    # Apply updates if not dry run
    if not dry_run:
        print("\n⚙️  Applying updates...")
        success_count = 0
        
        for update in updates_to_make:
            if db.update_transaction(update['_id'], {'spender': update['new_spender']}):
                success_count += 1
        
        print(f"\n✓ Successfully updated {success_count} transactions!")
        print(f"✗ Failed to update {len(updates_to_make) - success_count} transactions")
    else:
        print("\n💡 To apply these changes, run with dry_run=False")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate existing transactions to add spender field')
    parser.add_argument('--default-spender', 
                       choices=['Joint', 'Dmitry', 'Yaara'],
                       default='Joint',
                       help='Default spender for transactions without card patterns')
    parser.add_argument('--live', 
                       action='store_true',
                       help='Actually modify the database (default is dry-run)')
    
    args = parser.parse_args()
    
    migrate_existing_transactions(
        default_spender=args.default_spender,
        dry_run=not args.live
    )

if __name__ == "__main__":
    main()
