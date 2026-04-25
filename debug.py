#!/usr/bin/env python3
"""
Debug script for NeoTiers bot deployment issues
"""

import os
import sys

def check_env_vars():
    """Check critical environment variables"""
    print("=== Environment Variables Check ===")

    required_vars = [
        'DISCORD_TOKEN',
        'GUILD_ID',
    ]

    optional_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY',
        'DATABASE_URL',
        'WEBSITE_URL',
        'BOT_API_KEY',
    ]

    missing_required = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:20]}..." if len(str(value)) > 20 else f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: NOT SET")
            missing_required.append(var)

    print("\nOptional variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value[:20]}..." if len(str(value)) > 20 else f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var}: NOT SET")

    if missing_required:
        print(f"\n❌ MISSING REQUIRED VARIABLES: {', '.join(missing_required)}")
        return False

    print("\n✅ All required environment variables are set!")
    return True

def check_imports():
    """Check if required packages can be imported"""
    print("\n=== Import Check ===")

    required_imports = [
        'discord',
        'aiohttp',
    ]

    optional_imports = [
        'asyncpg',
    ]

    failed_imports = []

    for package in required_imports:
        try:
            __import__(package)
            print(f"✅ {package}: OK")
        except ImportError as e:
            print(f"❌ {package}: FAILED - {e}")
            failed_imports.append(package)

    for package in optional_imports:
        try:
            __import__(package)
            print(f"✅ {package}: OK (optional)")
        except ImportError:
            print(f"⚠️  {package}: NOT AVAILABLE (optional)")

    # Test bot creation
    try:
        import discord
        from discord.ext import commands

        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True

        test_bot = commands.Bot(command_prefix="!", intents=intents)
        print("✅ Bot object creation: OK")
    except Exception as e:
        print(f"❌ Bot creation failed: {e}")
        failed_imports.append("bot_creation")

    if failed_imports:
        print(f"\n❌ FAILED IMPORTS/CREATION: {', '.join(failed_imports)}")
        return False

    print("\n✅ All required imports and bot creation successful!")
    return True

def check_platform():
    """Check platform and environment info"""
    print("\n=== Platform Info ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Working directory: {os.getcwd()}")

    # Check if we're in a containerized environment
    if os.path.exists('/.dockerenv') or os.getenv('RENDER'):
        print("✅ Running in containerized environment (likely Render)")
    else:
        print("ℹ️  Running in local/development environment")

def main():
    print("NeoTiers Bot - Deployment Debug Script")
    print("=" * 50)

    env_ok = check_env_vars()
    import_ok = check_imports()
    check_platform()

    print("\n" + "=" * 50)
    if env_ok and import_ok:
        print("✅ Basic checks passed! The bot should be able to start.")
        print("\nIf the bot still won't start, check the Render logs for:")
        print("- Database connection errors")
        print("- Discord API errors")
        print("- Port binding issues (health server on 8080)")
    else:
        print("❌ Basic checks failed! Fix the issues above before deploying.")

    return 0 if (env_ok and import_ok) else 1

if __name__ == '__main__':
    sys.exit(main())