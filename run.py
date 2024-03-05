import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from logging import getLogger
from pathlib import Path
from random import random
from time import sleep
from xml.dom import minidom

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from tqdm import tqdm

load_dotenv()
logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class RSSFeed:
    def __init__(self, title, link, description):
        self.root = ET.Element("rss", version="2.0")
        self.channel = ET.SubElement(self.root, "channel")
        ET.SubElement(self.channel, "title").text = title
        ET.SubElement(self.channel, "link").text = link
        ET.SubElement(self.channel, "description").text = description
        self.format = "%a, %d %b %Y %H:%M:%S"

    def add_item(self, title, link, description, pubDate=None):
        item = ET.SubElement(self.channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "description").text = description
        if pubDate:
            ET.SubElement(item, "pubDate").text = pubDate.strftime(self.format)
        else:
            ET.SubElement(item, "pubDate").text = datetime.now().strftime(self.format)

    def export(self, filename):
        placeholder_date = datetime.min.strftime(self.format)

        def get_pubDate(item):
            pubDate_element = item.find("pubDate")
            return (
                pubDate_element.text
                if pubDate_element is not None and pubDate_element.text is not None
                else placeholder_date
            )

        # Adjusted format string to exclude timezone
        items = sorted(
            self.channel.findall("item"),
            key=lambda x: datetime.strptime(get_pubDate(x), self.format),
            reverse=True,
        )
        self.channel[:] = items

        rough_string = ET.tostring(self.root, "utf-8")
        reparsed = minidom.parseString(rough_string)
        pretty_string = reparsed.toprettyxml(indent="  ", encoding="utf-8")

        with open(filename, "wb") as file:
            file.write(pretty_string)


def initialize_webdriver():
    """Initialize and return a headless Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size("1080", "1920")
    return driver


def login_to_twitter(driver, username, password):
    """Log in to Twitter using the provided credentials."""
    twitter_base = "https://twitter.com/login/"
    driver.get(twitter_base)
    sleep(5)
    logger.info("sending username")
    driver.find_element(by=By.NAME, value="text").send_keys(username)
    driver.find_element(by=By.XPATH, value='//div/span/span[text()="Next"]').click()
    sleep(5)
    logger.info("sending password")
    driver.find_element(by=By.NAME, value="password").send_keys(password)
    driver.find_element(by=By.XPATH, value='//div/span/span[text()="Log in"]').click()
    sleep(5)
    logger.info("Logged in to Twitter")


def extract_twitter_link(url):
    # Define a regex pattern to match the desired URL format and capture the relevant parts
    pattern = r"(https://twitter\.com/[^/]+/status/\d+)/?"

    # Use the regex to search for a match in the input URL
    match = re.search(pattern, url)

    # If a match is found, return the matched URL (without any trailing components)
    if match:
        return match.group(1) + "/"
    else:
        # Return the original URL or an error message if no match is found
        return "Invalid Twitter URL"


if __name__ == "__main__":
    logger = getLogger(__name__)
    base_dir = Path(__file__).parent.absolute()

    driver = initialize_webdriver()
    login_to_twitter(driver, os.environ.get("USERNAME"), os.environ.get("PASSWORD"))

    feed = RSSFeed(
        title="スプラトゥーン3",
        link="https://twitter.com/SplatoonJP",
        description="スプラトゥーン3公式Twitter",
    )

    logger.info("accessing splatoonjp")
    driver.get("https://twitter.com/SplatoonJP")
    sleep(3 + 4 * random())
    n_elements = len(driver.find_elements(By.XPATH, '//*[@data-testid="cellInnerDiv"]'))

    logger.info(f"{n_elements} elements found")
    try:
        for i in tqdm(range(n_elements)):
            # for i in tqdm(range(3)):
            logger.info(f"[{i}] accessing splatoonjp")
            sleep(3 + 4 * random())
            # logger.info("scrolling...")
            # ActionChains(driver=driver).scroll_by_amount(0, 800).perform()
            # sleep(3 + 4 * random())

            logger.info(f"saved screenshot to : logged_in_{i}.png")
            driver.save_screenshot(f"logged_in_{i}.png")
            driver.find_elements(By.XPATH, '//*[@data-testid="cellInnerDiv"]')[
                i
            ].click()
            sleep(3 + 4 * random())

            time_element = driver.find_element(By.TAG_NAME, "time")
            datetime_value = time_element.get_attribute("datetime")
            if datetime_value is not None:
                pubDate_datetime = datetime.fromisoformat(
                    datetime_value[:-5]
                )  # Remove milliseconds for compatibility
            else:
                pubDate_datetime = None
            title = (
                driver.find_element(
                    By.XPATH, '//*[@data-testid="tweetText"]'
                ).text.replace("\n", "")[:50]
                + "..."
            )
            link = extract_twitter_link(driver.current_url)
            description = driver.find_element(
                By.XPATH, '//*[@data-testid="tweetText"]'
            ).text
            pubDate = pubDate_datetime
            logger.info(f"adding item {title} @ [{pubDate}]")
            feed.add_item(
                title=title,
                link=link,
                description=description,
                pubDate=pubDate,
            )
            sleep(3 + 4 * random())
            driver.back()
        feed.export(base_dir / "docs/assets/rss/rss.xml")
    except IndexError as e:
        logger.error(e)
        feed.export(base_dir / "docs/assets/rss/rss.xml")
    except Exception as e:
        logger.error(e)
        feed.export(base_dir / "docs/assets/rss/rss.xml")
        driver.save_screenshot("something_wrong.png")
        raise e
