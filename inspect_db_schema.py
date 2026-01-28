"""Quick script to inspect database schema for Phase 5A audit planning"""

import sqlite3
from pathlib import Path

db_path = Path("app/data/drafts.db")

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("="*80)
print("DATABASE SCHEMA INSPECTION - Phase 5A Audit Persistence Discovery")
print("="*80)

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print(f"\n📊 Found {len(tables)} table(s):\n")

for table in tables:
    table_name = table[0]
    print(f"{'='*80}")
    print(f"TABLE: {table_name}")
    print(f"{'='*80}")
    
    # Get table schema
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    schema = cursor.fetchone()[0]
    print(f"\nSchema DDL:")
    print(schema)
    
    # Get column info
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    print(f"\nColumns ({len(columns)}):")
    for col in columns:
        col_id, name, dtype, notnull, default, pk = col
        nullable = "NOT NULL" if notnull else "NULL"
        primary = "PRIMARY KEY" if pk else ""
        default_str = f"DEFAULT {default}" if default else ""
        print(f"  {col_id+1}. {name:20} {dtype:10} {nullable:10} {primary:15} {default_str}")
    
    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\nRow count: {count}")
    
    # Check for indexes
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'")
    indexes = cursor.fetchall()
    if indexes:
        print(f"\nIndexes ({len(indexes)}):")
        for idx in indexes:
            if idx[0]:  # Skip automatic indexes (None)
                print(f"  {idx[0]}")
    else:
        print("\nIndexes: None")
    
    print()

# Check database file size
import os
db_size_bytes = os.path.getsize(db_path)
db_size_kb = db_size_bytes / 1024
print(f"{'='*80}")
print(f"Database file size: {db_size_kb:.2f} KB ({db_size_bytes} bytes)")
print(f"{'='*80}")

# Check for any migration-related metadata
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%migration%' OR name LIKE '%version%'")
migration_tables = cursor.fetchall()
if migration_tables:
    print(f"\n⚠️ Migration-related tables found: {[t[0] for t in migration_tables]}")
else:
    print("\n✅ No migration tracking tables found (using manual ALTER TABLE approach)")

conn.close()

print(f"\n{'='*80}")
print("DISCOVERY COMPLETE")
print(f"{'='*80}")
