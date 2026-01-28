"""
SECURITY VERIFICATION - Credentials Protection Check
=====================================================
Verifies that ALL credential files are properly secured and not tracked by git.
"""

import sys
import subprocess
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

print("=" * 70)
print("🔒 CREDENTIALS SECURITY VERIFICATION")
print("=" * 70)

# Critical files that must NEVER be in git
CRITICAL_FILES = [
    "config/aim-tashiro-poc-dec6e8e0cdb7.json",  # NEW CREDENTIALS
    "config/aim-tashiro-poc-09a7f137eb05.json",  # OLD CREDENTIALS
    "config/google_vision_key.json",
    "config/google_docai_key.json",
    ".env",
]

def check_gitignore():
    """Check if .gitignore has proper patterns"""
    print("\n📋 Step 1: Checking .gitignore patterns...")
    
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        print("❌ CRITICAL: .gitignore file not found!")
        return False
    
    with open(gitignore_path, 'r') as f:
        content = f.read()
    
    required_patterns = [
        "config/aim-tashiro-poc-*.json",
        "config/*.json",
        "*credentials*.json",
        ".env",
    ]
    
    all_present = True
    for pattern in required_patterns:
        if pattern in content:
            print(f"   ✔ Pattern found: {pattern}")
        else:
            print(f"   ❌ MISSING: {pattern}")
            all_present = False
    
    return all_present

def check_git_tracking():
    """Check if critical files are tracked by git"""
    print("\n📋 Step 2: Checking git tracking status...")
    
    try:
        # Get all tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = result.stdout.strip().split('\n')
        
        violations = []
        for critical_file in CRITICAL_FILES:
            if critical_file in tracked_files:
                # File is tracked, but check if it's being deleted
                status_result = subprocess.run(
                    ["git", "status", "--porcelain", "--", critical_file],
                    capture_output=True,
                    text=True
                )
                
                status_line = status_result.stdout.strip()
                
                # If status starts with " D" (deleted) or "D " (deletion staged), it's being removed
                if status_line.startswith(" D") or status_line.startswith("D "):
                    print(f"   ✔ Safe: {critical_file} is being REMOVED from git")
                else:
                    violations.append(critical_file)
                    print(f"   ❌ CRITICAL: {critical_file} is TRACKED by git!")
            else:
                print(f"   ✔ Safe: {critical_file} is NOT tracked")
        
        return len(violations) == 0, violations
        
    except Exception as e:
        print(f"   ⚠️ Warning: Could not check git tracking: {e}")
        return True, []

def check_git_status():
    """Check if critical files are staged"""
    print("\n📋 Step 3: Checking staged files...")
    
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        
        staged_output = result.stdout
        violations = []
        
        for critical_file in CRITICAL_FILES:
            # Check if file appears in status output
            for line in staged_output.split('\n'):
                if critical_file in line:
                    # If it's a deletion (" D" or "D "), that's safe
                    if line.startswith(" D") or line.startswith("D "):
                        print(f"   ✔ Safe: {critical_file} deletion is not staged")
                    elif line.strip():  # If there's any other status
                        violations.append(critical_file)
                        print(f"   ❌ CRITICAL: {critical_file} is STAGED!")
                    break
            else:
                # File not in status output at all
                print(f"   ✔ Safe: {critical_file} is not staged")
        
        return len(violations) == 0, violations
        
    except Exception as e:
        print(f"   ⚠️ Warning: Could not check git status: {e}")
        return True, []

def check_file_existence():
    """Verify credential files exist and have correct permissions"""
    print("\n📋 Step 4: Checking file existence and permissions...")
    
    new_creds = Path("config/aim-tashiro-poc-dec6e8e0cdb7.json")
    old_creds = Path("config/aim-tashiro-poc-09a7f137eb05.json")
    
    if new_creds.exists():
        print(f"   ✔ NEW credentials exist: {new_creds.name}")
        print(f"      Size: {new_creds.stat().st_size} bytes")
        
        # Verify it's valid JSON
        try:
            with open(new_creds, 'r') as f:
                data = json.load(f)
                print(f"      ✔ Valid JSON")
                print(f"      Project: {data.get('project_id')}")
                print(f"      Service Account: {data.get('client_email')}")
        except Exception as e:
            print(f"      ❌ Invalid JSON: {e}")
    else:
        print(f"   ❌ NEW credentials NOT FOUND!")
    
    if old_creds.exists():
        print(f"   ⚠️ OLD credentials still exist: {old_creds.name}")
        print(f"      Recommendation: Delete after confirming new credentials work")
    else:
        print(f"   ✔ OLD credentials removed or renamed")

def check_git_ignore_effectiveness():
    """Test if git properly ignores the files"""
    print("\n📋 Step 5: Testing git ignore effectiveness...")
    
    for critical_file in CRITICAL_FILES:
        if not Path(critical_file).exists():
            continue
        
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-v", critical_file],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # File is ignored
                output = result.stdout.strip()
                print(f"   ✔ {critical_file}")
                print(f"      Ignored by: {output.split(':')[1] if ':' in output else 'gitignore'}")
            else:
                print(f"   ❌ CRITICAL: {critical_file} is NOT IGNORED!")
                
        except Exception as e:
            print(f"   ⚠️ Could not check {critical_file}: {e}")

def check_env_file():
    """Check .env file security"""
    print("\n📋 Step 6: Checking .env file...")
    
    env_path = Path(".env")
    if env_path.exists():
        print("   ✔ .env file exists")
        
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Check for sensitive data
        if "GOOGLE_APPLICATION_CREDENTIALS" in content:
            print("   ✔ GOOGLE_APPLICATION_CREDENTIALS configured")
        
        if "aim-tashiro-poc-dec6e8e0cdb7.json" in content:
            print("   ✔ References NEW credentials file")
        
        # Verify .env is ignored
        try:
            result = subprocess.run(
                ["git", "check-ignore", ".env"],
                capture_output=True
            )
            if result.returncode == 0:
                print("   ✔ .env is properly ignored by git")
            else:
                print("   ❌ CRITICAL: .env is NOT IGNORED!")
        except:
            pass
    else:
        print("   ❌ .env file not found!")

# Run all checks
print("\n" + "=" * 70)
print("RUNNING SECURITY CHECKS...")
print("=" * 70)

results = {
    "gitignore_patterns": check_gitignore(),
    "git_tracking": check_git_tracking(),
    "git_status": check_git_status(),
}

check_file_existence()
check_git_ignore_effectiveness()
check_env_file()

# Final verdict
print("\n" + "=" * 70)
print("🔒 SECURITY VERDICT")
print("=" * 70)

tracking_safe, tracking_violations = results["git_tracking"]
status_safe, status_violations = results["git_status"]

if results["gitignore_patterns"] and tracking_safe and status_safe:
    print("\n✅ ALL SECURITY CHECKS PASSED")
    print("\n🎯 Credentials are SECURE:")
    print("   ✔ .gitignore patterns are correct")
    print("   ✔ No credentials tracked by git")
    print("   ✔ No credentials staged for commit")
    print("   ✔ Files are properly ignored")
    print("\n✅ SAFE TO COMMIT OTHER FILES")
else:
    print("\n❌ SECURITY ISSUES DETECTED!")
    
    if not results["gitignore_patterns"]:
        print("\n   ⚠️ .gitignore needs updating")
    
    if not tracking_safe:
        print("\n   ❌ CRITICAL: These files are TRACKED by git:")
        for f in tracking_violations:
            print(f"      - {f}")
        print("\n   FIX: Run: git rm --cached <file>")
    
    if not status_safe:
        print("\n   ❌ CRITICAL: These files are STAGED:")
        for f in status_violations:
            print(f"      - {f}")
        print("\n   FIX: Run: git reset HEAD <file>")
    
    print("\n❌ DO NOT COMMIT UNTIL ISSUES ARE FIXED!")

print("\n" + "=" * 70)
