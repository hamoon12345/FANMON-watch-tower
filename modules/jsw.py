import os
import subprocess
import requests
import json
import time
import sys
import re
from mysql.connector import connect, Error
from discord_webhook import DiscordWebhook
from urllib.parse import urlparse

CONFIG = {
    "scope_files": ["scopeyour.txt"],
    "katana_path": "katana",
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "yourpassword",
    "mysql_database": "js_watcher_sql",
    "discord_webhook": "yourwebhook",
    "check_interval": 600,
    "katana_timeout": 300,
    "katana_depth": 3,
    "max_urls_per_notification": 25,
    "verbose": True  
}

def print_verbose(message):
    if CONFIG["verbose"]:
        print(message)

def load_urls_from_files(file_paths):

    urls = set()
    for file_path in file_paths:
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):

                        if re.match(r'^https?://', url):
                            urls.add(url)
                        else:
                            urls.add(f"https://{url}")
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
    return list(urls)

def setup_database():

    max_retries = 3
    for attempt in range(max_retries):
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
            CREATE TABLE IF NOT EXISTS parameters (
                id INT AUTO_INCREMENT PRIMARY KEY,
                url VARCHAR(512) NOT NULL,
                parameters TEXT,
                source_domain VARCHAR(255),
                discovery_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_url (url)
            )
            """)
            connection.commit()
            print_verbose("Database setup complete")
            return True
        except Error as e:
            print(f"Database setup attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                return False
            time.sleep(5)
        finally:
            if 'connection' in locals() and connection.is_connected():
                cursor.close()
                connection.close()

def run_katana(url):

    try:
        cmd = [
            CONFIG["katana_path"],
            "-u", url,
            "-d", str(CONFIG["katana_depth"]),
            "-jc", "-kf", "all",
            "-silent"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CONFIG["katana_timeout"]
        )
        
        param_urls = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue


            if not re.search(r'\.js(\?.*)?$', line):
                continue


            if urlparse(line).netloc != urlparse(url).netloc:
                continue


            if '?' not in line and any(line.endswith(ext) for ext in ['.css', '.png', '.jpg', '.gif']):
                continue

            param_urls.add(line)
        
        return list(param_urls)
    
    except subprocess.TimeoutExpired:
        print_verbose(f"Katana timeout for {url}")
    except Exception as e:
        print(f"Katana error for {url}: {str(e)}")
    return []

def get_existing_urls():

    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()
        cursor.execute("SELECT url FROM parameters")
        return {row[0] for row in cursor.fetchall()}
    except Error as e:
        print(f"Database error: {e}")
        return set()
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def save_new_urls(new_urls, source_domain):

    if not new_urls:
        return 0
    
    try:
        connection = connect(
            host=CONFIG["mysql_host"],
            user=CONFIG["mysql_user"],
            password=CONFIG["mysql_password"],
            database=CONFIG["mysql_database"]
        )
        cursor = connection.cursor()
        
        batch_size = 100
        new_count = 0
        
        for i in range(0, len(new_urls), batch_size):
            batch = new_urls[i:i + batch_size]
            values = []
            
            for url in batch:
                params = {}
                if '?' in url:
                    query = url.split('?', 1)[1]
                    params = dict([pair.split('=', 1) if '=' in pair else (pair, '') for pair in query.split('&')])
                
                values.append((url, json.dumps(params), source_domain))
            
            try:
                cursor.executemany("""
                    INSERT IGNORE INTO parameters (url, parameters, source_domain)
                    VALUES (%s, %s, %s)
                """, values)
                new_count += cursor.rowcount
            except Error as e:
                print(f"Batch insert error: {e}")
        
        connection.commit()
        return new_count
    except Error as e:
        print(f"Database save error: {e}")
        return 0
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def send_discord_notification(new_urls, source_domain):

    if not new_urls:
        return
    
    chunks = [new_urls[i:i + CONFIG["max_urls_per_notification"]] 
             for i in range(0, len(new_urls), CONFIG["max_urls_per_notification"])]
    
    for chunk in chunks:
        message = f"🚨 **New JS found for {source_domain}** 🚨\n"
        message += f"Total new JS: {len(new_urls)}\n\n"
        message += "\n".join(f"• {url}" for url in sorted(chunk)[:CONFIG["max_urls_per_notification"]])
        
        try:
            webhook = DiscordWebhook(
                url=CONFIG["discord_webhook"],
                content=message,
                rate_limit_retry=True
            )
            response = webhook.execute()
            if response.status_code != 200:
                print(f"Discord notification failed: {response.status_code}")
        except Exception as e:
            print(f"Notification error: {e}")

def monitor_urls():

    if not setup_database():
        print("Failed to setup database. Exiting.")
        return
    
    while True:
        try:
            urls = load_urls_from_files(CONFIG["scope_files"])
            if not urls:
                print_verbose("No JS found. Waiting...")
                time.sleep(CONFIG["check_interval"])
                continue
                
            existing_urls = get_existing_urls()
            total_new = 0
            
            for url in urls:
                print_verbose(f"\nChecking: {url}")
                domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
                
                katana_results = run_katana(url)
                new_urls = [u for u in katana_results if u not in existing_urls]
                
                if new_urls:
                    print(f"Found {len(new_urls)} new JS for {domain}")
                    saved = save_new_urls(new_urls, domain)
                    print(f"Saved {saved} new JS")
                    send_discord_notification(new_urls, domain)
                    total_new += saved
            
            print_verbose(f"\nCycle complete. Found {total_new} total new JS.")
            print_verbose(f"Waiting {CONFIG['check_interval']} seconds...\n")
            time.sleep(CONFIG["check_interval"])
            
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
            break
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    monitor_urls()