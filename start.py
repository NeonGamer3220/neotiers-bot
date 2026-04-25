#!/usr/bin/env python3
"""
Startup script for Render deployment
"""

import os
import sys
import subprocess

def run_debug():
    """Run the debug script first"""
    print("Running debug checks...")
    result = subprocess.run([sys.executable, 'debug.py'], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode == 0

def main():
    """Main startup function"""
    print("NeoTiers Bot - Render Startup")
    print("=" * 40)

    # Run debug checks
    if not run_debug():
        print("❌ Debug checks failed, aborting startup")
        sys.exit(1)

    print("\n✅ Debug checks passed, starting bot...")

    # Start the bot
    os.execv(sys.executable, [sys.executable, 'main.py'])

if __name__ == '__main__':
    main()