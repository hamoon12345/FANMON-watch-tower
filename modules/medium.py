import requests
from bs4 import BeautifulSoup
import logging
import time


logging.basicConfig(level=logging.INFO)


def get_bug_bounty_writeups(url):
    try:

        response = requests.get(url)
        response.raise_for_status() 
        soup = BeautifulSoup(response.text, 'html.parser')


        writeups = []
        articles = soup.find_all('article') 

        for article in articles:
            title_tag = article.find('h2')  
            link_tag = article.find('a', href=True)  

            if title_tag and link_tag:
                title = title_tag.get_text()
                url = link_tag['href']  
                full_url = f"https://medium.com{url}"  
                writeups.append((title, full_url))

        logging.info(f"Found {len(writeups)} write-ups.")
        return writeups

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data from URL: {e}")
        return []


def send_discord_notification(webhook_url, message):
    try:
        payload = {
            "content": message
        }
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()  
        logging.info(f"Sent notification to Discord: {message}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending Discord notification: {e}")


def monitor_bug_bounty_writeups(webhook_url, url_to_scrape):

    writeups = get_bug_bounty_writeups(url_to_scrape)


    for title, url in writeups:
        message = f"New Bug Bounty Write-up: {title}\nRead here: {url}"
        send_discord_notification(webhook_url, message)


def run_monitoring_task():
    webhook_url = 'yourwebhook'  # Replace with your actual Discord webhook URL
    url_to_scrape = 'https://medium.com/tag/bug-bounty' 

    while True:
        logging.info("Checking for new write-ups...")
        monitor_bug_bounty_writeups(webhook_url, url_to_scrape)
        time.sleep(3600)  

if __name__ == "__main__":
    run_monitoring_task()