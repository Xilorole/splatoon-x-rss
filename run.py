import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from logging import getLogger
from pathlib import Path
from random import random
from time import sleep
from typing import Optional, Set
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
    def __init__(self, title: str, link: str, description: str):
        """
        Initialize an RSSFeed object.

        Parameters
        ----------
        title : str
            The title of the RSS feed.
        link : str
            The link to the RSS feed.
        description : str
            The description of the RSS feed.
        """
        self.root = ET.Element("rss", version="2.0")
        self.channel = ET.SubElement(self.root, "channel")
        ET.SubElement(self.channel, "title").text = title
        ET.SubElement(self.channel, "link").text = link
        ET.SubElement(self.channel, "description").text = description
        self.format = "%a, %d %b %Y %H:%M:%S"
        self.registered: Set[str] = set()

    def add_item(
        self,
        title: str,
        link: str,
        description: str,
        pubDate: Optional[datetime] = None,
    ):
        """
        Add an item to the RSS feed.

        Parameters
        ----------
        title : str
            The title of the item.
        link : str
            The link to the item.
        description : str
            The description of the item.
        pubDate : datetime, optional
            The publication date of the item, by default None.
        """
        if link in self.registered:
            logger.info(f'The object already exists "{title}". Skipped.')
        else:
            item = ET.SubElement(self.channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = description
            pub_date_text = (
                pubDate.strftime(self.format)
                if pubDate
                else datetime.now().strftime(self.format)
            )
            ET.SubElement(item, "pubDate").text = pub_date_text
            self.registered.add(link)

    def is_registered(self, url: str) -> bool:
        """
        Check if a URL is registered in the RSS feed.

        Parameters
        ----------
        url : str
            The URL to check.

        Returns
        -------
        bool
            True if the URL is registered, False otherwise.
        """
        return url in self.registered

    def export(self, filename: os.PathLike):
        """
        Export the RSS feed to an XML file.

        Parameters
        ----------
        filename : str
            The name of the file to export the RSS feed to.
        """
        placeholder_date = datetime.min.strftime(self.format)

        def get_pubDate(item: ET.Element) -> str:
            pubDate_element = item.find("pubDate")
            return (
                pubDate_element.text
                if pubDate_element is not None and pubDate_element.text
                else placeholder_date
            )

        items = self.channel.findall("item")
        sorted_items = sorted(
            items,
            key=lambda x: datetime.strptime(get_pubDate(x), self.format),
            reverse=True,
        )

        # Remove existing items from the channel
        for item in items:
            self.channel.remove(item)

        # Append the sorted items to the channel
        for item in sorted_items:
            self.channel.append(item)

        rough_string = ET.tostring(self.root, "utf-8")
        reparsed = minidom.parseString(rough_string)
        pretty_string = reparsed.toprettyxml(indent="  ", encoding="utf-8")

        with open(filename, "wb") as file:
            file.write(pretty_string)

    @classmethod
    def import_from_file(cls, filename: os.PathLike) -> Optional["RSSFeed"]:
        """
        Import an RSS feed from an XML file.

        Parameters
        ----------
        filename : str
            The name of the XML file to import the RSS feed from.

        Returns
        -------
        Optional['RSSFeed']
            An instance of the RSSFeed class if the import is successful, None otherwise.
        """
        try:
            tree = ET.parse(filename)
            root = tree.getroot()

            if root.tag != "rss" or root.get("version") != "2.0":
                logger.error(f"Invalid RSS format in file: {filename}")
                return None

            channel = root.find("channel")
            if channel is None:
                logger.error(f"Channel element not found in file: {filename}")
                return None

            title = channel.findtext("title")
            link = channel.findtext("link")
            description = channel.findtext("description")

            if title is None or link is None or description is None:
                logger.error(f"Missing required elements in file: {filename}")
                return None

            rss_feed = cls(title, link, description)

            for item in channel.findall("item"):
                item_title = item.findtext("title")
                item_link = item.findtext("link")
                item_description = item.findtext("description")
                item_pubDate_text = item.findtext("pubDate")

                if item_title is None or item_link is None or item_description is None:
                    logger.warning(f"Missing required elements in item: {item_title}")
                    continue

                item_pubDate = None
                if item_pubDate_text:
                    try:
                        item_pubDate = datetime.strptime(
                            item_pubDate_text, rss_feed.format
                        )
                    except ValueError:
                        logger.warning(f"Invalid pubDate format in item: {item_title}")

                rss_feed.add_item(item_title, item_link, item_description, item_pubDate)

            return rss_feed

        except FileNotFoundError:
            logger.error(f"File not found: {filename}")
            return None

        except ET.ParseError:
            logger.error(f"Error parsing XML file: {filename}")
            return None


class Tweet:
    def __init__(self, driver: webdriver.Chrome, target_text: Optional[str]):
        if target_text:
            tweet_elements = list(
                filter(
                    lambda e: e.text == target_text,
                    driver.find_elements(By.XPATH, '//*[@data-testid="tweetText"]'),
                )
            )
            if len(tweet_elements) == 0:
                logging.error(f"no element detected with target_text: {target_text}")
                top_1 = sorted(
                    driver.find_elements(By.XPATH, '//*[@data-testid="tweetText"]'),
                    key=(lambda x: -Levenshtein.ratio(x.text, target_text)),
                )[0]

                logging.error(
                    f"most matching item is {top_1.text} @ {Levenshtein.ratio(top_1.text, target_text)}"
                )
                if (
                    Levenshtein.ratio(
                        re.sub(r"https?:.*(?=\s)", "", top_1.text),
                        re.sub(r"https?:.*(?=\s)", "", target_text),
                    )
                    > 0.95
                ):
                    tweet_element = top_1
                else:
                    raise NoSuchElementException
            else:
                tweet_element = tweet_elements[0]
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
                    logger.warning("multiple time tag found")
                    logger.warning(
                        "seems to be inline item card expanded. taking last."
                    )
                    datetime_value: Optional[str] = time_elements[-1].get_attribute(
                        "datetime"
                    )
                    break

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


def rep(x: str) -> str:
    return x.replace("\n", "")


if __name__ == "__main__":
    base_dir = Path(".").parent.absolute()
    export_path = base_dir / "docs/assets/rss/rss.xml"

    if export_path.exists():
        logger.info(f"loading '{export_path}'")
        feed = RSSFeed.import_from_file(export_path)
        if feed is None:
            feed = RSSFeed(
                title="スプラトゥーン3",
                link="https://twitter.com/SplatoonJP",
                description="スプラトゥーン3公式Twitter",
            )
    else:
        feed = RSSFeed(
            title="スプラトゥーン3",
            link="https://twitter.com/SplatoonJP",
            description="スプラトゥーン3公式Twitter",
        )
    logger.info("initializing webdriver")
    driver = initialize_webdriver()
    login_to_twitter(driver, os.environ.get("USERNAME"), os.environ.get("PASSWORD"))

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
        logger.info(f"  - [{i}] {rep(element_text)[:20]}")

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
        element.click()
        sleep(3 + 4 * random())
        WebDriverWait(driver, 10).until(
            lambda x: x.find_elements(By.XPATH, '//*[@data-testid="tweetText"]')
        )

        tweet = Tweet(driver, target_text=element_text)

        # search splatoon JP in link
        cond_link = not re.search(
            "SplatoonJP|nintendo_cs|Nintendo", extract_twitter_link(tweet.link)
        )
        cond_title = Levenshtein.ratio(tweet.description, element_text) < 0.7
        cond_registered = feed.is_registered(tweet.link)

        if cond_link or cond_title or cond_registered:
            logger.info(f"skipping {rep(tweet.title)}")
            if cond_link:
                logger.info(f"link is not splatoon: {tweet.link}")
            if cond_title:
                logger.info(
                    f"title is not same @ {Levenshtein.ratio(tweet.description, element_text):.2f}"
                )
                logger.info(f"TARGET: {rep(element_text)}")
                logger.info(f"ACCESS: {rep(tweet.description)}")
            if cond_registered:
                logger.info(f"link is already registered: {tweet.title}")
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
    feed.export(export_path)
