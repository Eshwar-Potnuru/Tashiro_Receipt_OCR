"""Fix repository to support :memory: databases for testing."""

# Read the file
with open('app/repositories/draft_repository.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and replace key sections
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 1. Update __init__ docstring
    if '            db_path: Path to SQLite database file. If None, uses default' in line:
        new_lines.append(line)
        i += 1
        new_lines.append('                    location at app/data/drafts.db. Special value ":memory:"\n')
        i += 1  # skip the old location line
        new_lines.append('                    creates an in-memory database for testing.\n')
    # 2. Add memory connection setup after self.db_path
    elif line.strip() == 'self.db_path = db_path' and 'self._init_schema()' in lines[i+1]:
        new_lines.append(line)
        new_lines.append('        \n')
        new_lines.append('        # For :memory: databases, keep a persistent connection\n')
        new_lines.append('        # (otherwise each new connection creates a fresh empty database)\n')
        new_lines.append('        self._memory_conn = None\n')
        new_lines.append('        if db_path == ":memory:":\n')
        new_lines.append('            self._memory_conn = sqlite3.connect(":memory:")\n')
        new_lines.append('            self._memory_conn.row_factory = sqlite3.Row\n')
        new_lines.append('        \n')
    # 3. Add _get_connection method before _init_schema
    elif line.strip() == 'def _init_schema(self) -> None:':
        # Insert _get_connection method
        new_lines.append('    def _get_connection(self) -> sqlite3.Connection:\n')
        new_lines.append('        """Get a database connection.\n')
        new_lines.append('        \n')
        new_lines.append('        For :memory: databases, returns the persistent connection.\n')
        new_lines.append('        For file databases, creates a new connection.\n')
        new_lines.append('        """\n')
        new_lines.append('        if self._memory_conn is not None:\n')
        new_lines.append('            return self._memory_conn\n')
        new_lines.append('        return sqlite3.connect(self.db_path)\n')
        new_lines.append('\n')
        new_lines.append(line)
    # 4. Replace sqlite3.connect(self.db_path) with _get_connection()
    elif '        conn = sqlite3.connect(self.db_path)' in line:
        indent = line[:line.index('conn')]
        new_lines.append(f'{indent}conn = self._get_connection()\n')
        # Add should_close flag
        new_lines.append(f'{indent}should_close = (self._memory_conn is None)\n')
        # If next line sets row_factory, add it
        if i+1 < len(lines) and 'conn.row_factory' in lines[i+1]:
            i += 1
            new_lines.append(lines[i])
    # 5. Replace conn.close() with conditional close
    elif '            conn.close()' in line:
        indent = line[:line.index('conn')]
        new_lines.append(f'{indent}if should_close:\n')
        new_lines.append(f'{indent}    conn.close()\n')
    else:
        new_lines.append(line)
    
    i += 1

# Write back
with open('app/repositories/draft_repository.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed repository file for :memory: database support")
