#!/usr/bin/env python
"""Reset databases to fresh state for GitHub deployment.

This script creates fresh, empty database files suitable for version control.
The databases will be automatically recreated and seeded when the app starts.
"""

import sqlite3
from pathlib import Path

def reset_databases():
    """Reset all database files to empty state."""
    
    data_dir = Path(__file__).parent / "app" / "Data"
    
    # Database files to reset
    db_files = {
        "drafts.db": """
            CREATE TABLE IF NOT EXISTS draft_receipts (
                draft_id TEXT PRIMARY KEY,
                receipt_json TEXT NOT NULL,
                status TEXT DEFAULT 'DRAFT',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                image_ref TEXT,
                image_data TEXT,
                created_by TEXT,
                send_attempt_count INTEGER DEFAULT 0,
                last_send_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_status ON draft_receipts(status);
            CREATE INDEX IF NOT EXISTS idx_created_by ON draft_receipts(created_by);
            CREATE INDEX IF NOT EXISTS idx_created_at ON draft_receipts(created_at);
        """,
        "audit.db": """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                login_id TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                name TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_login_id ON users(login_id);
            CREATE INDEX IF NOT EXISTS idx_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_role ON users(role);
            
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user TEXT,
                action TEXT,
                details TEXT,
                ip_address TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_user ON audit_log(user);
        """
    }
    
    for db_name, schema in db_files.items():
        db_path = data_dir / db_name
        
        # Backup existing database
        if db_path.exists():
            backup_path = db_path.with_suffix('.db.backup')
            print(f"📦 Backing up {db_name} to {backup_path.name}")
            db_path.rename(backup_path)
        
        # Create fresh database
        print(f"🔄 Creating fresh {db_name}...")
        conn = sqlite3.connect(db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()
        
        # Check new size
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"✓ {db_name} created - Size: {size_mb:.2f} MB")
    
    print("\n✅ All databases reset successfully!")
    print("📝 Note: Databases will be auto-seeded when the app starts in dev mode")
    print("🔒 Original databases backed up with .backup extension")

if __name__ == "__main__":
    reset_databases()
