import os
import subprocess
import requests
import json
import time
import sys
import re
from mysql.connector import connect, Error
from discord_webhook import DiscordWebhook
from datetime import datetime
from discord_webhook import DiscordWebhook, DiscordEmbed
# Configuration
CONFIG = {
    "scope_files": ["yourscope.txt"],
    "dnsx_path": "dnsx",
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "yourmysqlpassword",
    "mysql_database": "ips",
    "discord_webhook": "yourwebhook",
    "check_interval": 3600  # 10 minutes in seconds
}

def load_domains_from_files(file_paths):
    """Load domains from scope files"""
    domains = set()

    for file_path in file_paths:
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    domain = line.strip()
                    if domain and not domain.startswith('#'):
                        domains.add(domain)
        except FileNotFoundError:
            print(f"Scope file not found: {file_path}")
        except Exception as e:
            print(f"Error reading scope file {file_path}: {e}")

    return list(domains)

def setup_database():
    """Create database and table if they don't exist"""
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"]
        )
        cursor = connection.cursor()

        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {CONFIG['mysql_database']}")
        cursor.execute(f"USE {CONFIG['mysql_database']}")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ips (
            id INT AUTO_INCREMENT PRIMARY KEY,
            domain VARCHAR(255) NOT NULL,
            ip VARCHAR(255) NOT NULL,
            discovery_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_ip (domain, ip)
        )
        """)


        connection.commit()
        cursor.close()
        connection.close()
        print("Database setup complete")
    except Error as e:
        print(f"Database setup error: {e}")


def run_dnsx(domain):
    """Run dnsx to find IP addresses"""
    try:
        echo_input = subprocess.Popen(
            ["echo", domain],
            stdout=subprocess.PIPE
        )
        result = subprocess.run(
            [CONFIG["dnsx_path"], "-a", "-resp-only", "--silent"],
            stdin=echo_input.stdout,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"dnsx error for {domain}: {e}")
        return []


def get_existing_ips(domain):
    """Get existing ips from database"""
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ip FROM ips WHERE domain = %s
        """, (domain,))
        results = cursor.fetchall()
        return {result[0] for result in results}
    except Error as e:
        print(f"Database query error: {e}")
        return set()
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()



def save_new_ips(domain, ips):
    """Save new ips to database"""
    if not ips:
        return 0

    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()

        new_count = 0
        for ip in ips:
            try:
                cursor.execute("""
                    INSERT INTO ips (domain, ip)
                    VALUES (%s, %s)
                """, (domain, ip))
                new_count += 1
            except Error as e:
                if "Duplicate entry" not in str(e):
                    print(f"Error saving ip {ip}: {e}")

        connection.commit()
        return new_count
    except Error as e:
        print(f"Database save error: {e}")
        return 0
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def send_discord_notification(domain, new_ips):
    """Send beautiful notification to Discord"""
    if not new_ips:
        return

    webhook = DiscordWebhook(
        url=CONFIG["discord_webhook"],
        rate_limit_retry=True
    )

    embed = DiscordEmbed(
        title=f'🚨 New IPs Found for {domain} 🚨',
        color='FF0000'  # Red color
    )

    embed.add_embed_field(
        name='🧠 New IPs',
        value="\n".join(f'{ip}' for ip in new_ips),
        inline=False
    )

    embed.add_embed_field(
        name='📅 Detected At',
        value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        inline=True
    )

    embed.add_embed_field(
        name='🌐 Scope',
        value=", ".join(CONFIG["scope_files"]),
        inline=True
    )

    embed.set_timestamp()

    webhook.add_embed(embed)

    try:
        response = webhook.execute()
        if response.status_code != 200:
            print(f"Discord notification failed: {response.status_code}")
    except Exception as e:
        print(f"Error sending Discord notification: {e}")

def monitor_domains():
    """Main monitoring function"""
    setup_database()

    while True:
        domains = load_domains_from_files(CONFIG["scope_files"])

        if not domains:
            print("No domains found in scope files. Waiting for next check...")
            time.sleep(CONFIG["check_interval"])
            continue

        for domain in domains:
            print(f"\nChecking ips for {domain}...")

            existing = get_existing_ips(domain)

            ips_get = run_dnsx(domain)

            all_ips = set(ips_get)
            new_ips = [sub for sub in all_ips if sub not in existing]

            if new_ips:
                print(f"Found {len(new_ips)} new ips for {domain}")
                saved_count = save_new_ips(domain, new_ips)
                print(f"Saved {saved_count} new ips to database")
                send_discord_notification(domain, new_ips)
            else:
                print(f"No new ips found for {domain}")

        print(f"\nWaiting {CONFIG['check_interval']} seconds for next check...")
        time.sleep(CONFIG["check_interval"])

if __name__ == "__main__":
    try:
        monitor_domains()
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)