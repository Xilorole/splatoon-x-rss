import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from logging import getLogger
from pathlib import Path
from random import random
from time import sleep
from typing import Optional
from xml.dom import minidom

import Levenshtein
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

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
        """_summary_

        Parameters
        ----------
        title : _type_
            _description_
        link : _type_
            _description_
        description : _type_
            _description_
        """
        self.root = ET.Element("rss", version="2.0")
        self.channel = ET.SubElement(self.root, "channel")
        ET.SubElement(self.channel, "title").text = title
        ET.SubElement(self.channel, "link").text = link
        ET.SubElement(self.channel, "description").text = description
        self.format = "%a, %d %b %Y %H:%M:%S"

        self.registered = set()

    def add_item(self, title, link, description, pubDate=None):
        """_summary_

        Parameters
        ----------
        title : _type_
            _description_
        link : _type_
            _description_
        description : _type_
            _description_
        pubDate : _type_, optional
            _description_, by default None
        """
        if link in self.registered:
            logger.info(f'the object already exists "{title}". skipped.')
        else:
            item = ET.SubElement(self.channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = description
            if pubDate:
                ET.SubElement(item, "pubDate").text = pubDate.strftime(self.format)
            else:
                ET.SubElement(item, "pubDate").text = datetime.now().strftime(
                    self.format
                )
            self.registered |= {link}

    def is_registered(self, url: str) -> bool:
        return url in self.registered

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


class Tweet:
    def __init__(self, driver: webdriver.Chrome, target_text: Optional[str]):
        if target_text:
            tweet_element = list(
                filter(
                    lambda e: e.text == target_text,
                    driver.find_elements(By.XPATH, '//*[@data-testid="tweetText"]'),
                )
            )[0]
        else:
            tweet_element = driver.find_element(
                By.XPATH, '//*[@data-testid="tweetText"]'
            )

        parent_element = driver.find_element(By.ID, tweet_element.get_attribute("id"))
        while True:
            try:
                time_elements = parent_element.find_elements(By.TAG_NAME, "time")
                if len(time_elements) == 1:
                    datetime_value: Optional[str] = time_elements[0].get_attribute(
                        "datetime"
                    )
                    break
                elif len(time_elements) > 1:
                    raise ValueError(
                        "Multiple time elements found within the same parent."
                    )
                else:
                    parent_element = parent_element.find_element(By.XPATH, "..")
            except NoSuchElementException:
                raise ValueError("No time element found within the hierarchy.")

        if datetime_value is not None:
            self.pubDate_datetime: Optional[datetime] = datetime.fromisoformat(
                datetime_value[:-5]
            )  # Remove milliseconds for compatibility
        else:
            self.pubDate_datetime: Optional[datetime] = None
        self.link: str = extract_twitter_link(driver.current_url)
        self.description: str = tweet_element.text
        self.title: str = self.description.replace("\n", "")[:50] + "..."


def initialize_webdriver(headless=True):
    """Initialize and return a headless Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disk-cache-dir=./.cache")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size("1080", "1920")
    return driver


def login_to_twitter(driver, username, password, sleep_time=5):
    """Log in to Twitter using the provided credentials."""
    twitter_base = "https://twitter.com/login/"
    driver.get(twitter_base)
    sleep(sleep_time)
    logger.info("sending username")
    WebDriverWait(driver, sleep_time).until(
        lambda x: x.find_element(by=By.NAME, value="text")
        and x.find_element(by=By.XPATH, value='//div/span/span[text()="Next"]')
    )
    sleep(sleep_time)
    driver.find_element(by=By.NAME, value="text").send_keys(username)
    driver.find_element(by=By.XPATH, value='//div/span/span[text()="Next"]').click()
    sleep(sleep_time)
    logger.info("sending password")
    WebDriverWait(driver, sleep_time).until(
        lambda x: x.find_element(by=By.NAME, value="password")
        and x.find_element(by=By.XPATH, value='//div/span/span[text()="Log in"]')
    )
    driver.find_element(by=By.NAME, value="password").send_keys(password)
    driver.find_element(by=By.XPATH, value='//div/span/span[text()="Log in"]').click()
    sleep(sleep_time)
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
    base_dir = Path(".").parent.absolute()

    logger.info("initializing webdriver")
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
    WebDriverWait(driver, 10).until(
        lambda x: x.find_element(By.XPATH, '//*[@data-testid="cellInnerDiv"]')
    )

    # まず最初に最新のテキストの一覧を取得して、そのテキストと一致しているものがあれば取得するにように調整するほうがいいか？
    element_texts = []
    for element in driver.find_elements(By.XPATH, '//*[@data-testid="tweetText"]'):
        element_texts.append(element.text)
    logger.info(f"{len(element_texts)} elements found")
    for i, element_text in enumerate(element_texts):
        logger.info(f"  - [{i}] {element_text.replace("\n","")[:20]}")

    for element_text in element_texts:
        sleep(3 + 4 * random())
        element = list(
            filter(
                lambda e: element_text == e.text,
                driver.find_elements(By.XPATH, '//*[@data-testid="tweetText"]'),
            )
        )[0]

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        sleep(1 + random())

        # click item
        logger.info(f"clicking item with text {element.text[:50].replace('\n','')}")
        element.click()
        sleep(3 + 4 * random())
        tweet = Tweet(driver, target_text=element_text)

        # search splatoon JP in link
        cond_link = not re.search(
            "SplatoonJP|nintendo_cs|Nintendo", extract_twitter_link(tweet.link)
        )
        cond_title = Levenshtein.ratio(tweet.description, element_text) < 0.7
        cond_registered = feed.is_registered(tweet.link)

        if cond_link or cond_title or cond_registered:
            logger.info(f"skipping {tweet.title.replace('\n','')}")
            if cond_link:
                logger.error(f"link is not splatoon: {tweet.link}")
            if cond_title:
                logger.error(
                    f"title is not same @ {Levenshtein.ratio(tweet.description, element_text):.2f}"
                )
                logger.error(f"TARGET: {element_text.replace('\n','')}")
                logger.error(f"ACCESS: {tweet.description.replace('\n','')}")
            if cond_registered:
                logger.error(f"link is already registered: {tweet.title}")
            driver.back()
            continue

        logger.info(f"adding item {tweet.title[:20]} @ [{tweet.pubDate_datetime}]")
        feed.add_item(
            title=tweet.title,
            link=tweet.link,
            description=tweet.description,
            pubDate=tweet.pubDate_datetime,
        )
        sleep(3 + 4 * random())
        driver.back()
    feed.export(base_dir / "docs/assets/rss/rss.xml")
