import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from random import random
from time import sleep

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from tqdm import tqdm

load_dotenv()


class RSSFeed:
    def __init__(self, title, link, description):
        self.root = ET.Element("rss", version="2.0")
        self.channel = ET.SubElement(self.root, "channel")
        ET.SubElement(self.channel, "title").text = title
        ET.SubElement(self.channel, "link").text = link
        ET.SubElement(self.channel, "description").text = description

    def add_item(self, title, link, description, pubDate=None):
        item = ET.SubElement(self.channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "description").text = description
        if pubDate:
            ET.SubElement(item, "pubDate").text = pubDate.strftime(
                "%a, %d %b %Y %H:%M:%S %z"
            )
        else:
            ET.SubElement(item, "pubDate").text = datetime.now().strftime(
                "%a, %d %b %Y %H:%M:%S %z"
            )

    def export(self, filename):
        tree = ET.ElementTree(self.root)
        tree.write(filename, encoding="utf-8", xml_declaration=True)


webdriver.Chrome()
options = webdriver.ChromeOptions()
# ヘッドレスモードに
options.add_argument("--headless")
options.add_argument("--no-sandbox")
# ブラウザーを起動
driver = webdriver.Chrome(options=options)
driver.set_window_size(
    "1080", "1920"
)  # 大事。デフォルトが800*600になっている。headlessだと要素部分が表示されないことがあるため。

twitter_base = "https://twitter.com/" + "login/"
account = os.environ.get("USERNAME")
password = os.environ.get("PASSWORD")

# ログインページを開く
driver.get(twitter_base)
time.sleep(5)

# account入力
element_account = driver.find_element(by=By.NAME, value="text")
element_account.send_keys(account)

# デバッグ1
driver.save_screenshot("①ログインID入力画面.png")

driver.find_element(by=By.XPATH, value='//div/span/span[text()="Next"]')

# 次へボタンクリック
element_login_next = driver.find_element(
    by=By.XPATH, value='//div/span/span[text()="Next"]'
)
# print(element_login_next)
# driver.close()
# exit()

# 画像のリンクをクリック
element_login_next.click()
time.sleep(5)

# パスワード入力
element_pass = driver.find_element(by=By.NAME, value="password")
element_pass.send_keys(password)

# ログインボタンクリック
element_login = driver.find_element(
    by=By.XPATH, value='//div/span/span[text()="Log in"]'
)
# print(element_login)
# driver.close()
# exit()

# デバッグ2
driver.save_screenshot("②ログインPW入力画面.png")
# driver.close()
# exit()

element_login.click()
time.sleep(5)


feed = RSSFeed(
    title="スプラトゥーン3",
    link="https://twitter.com/SplatoonJP",
    description="スプラトゥーン3公式Twitter",
)


driver.get("https://twitter.com/SplatoonJP")
sleep(3 + 4 * random())
n_elements = len(driver.find_elements(By.XPATH, '//*[@data-testid="cellInnerDiv"]'))

try:
    # for i in tqdm(range(n_elements)):
    for i in tqdm(range(2)):
        driver.get("https://twitter.com/SplatoonJP")
        sleep(3 + 4 * random())
        driver.find_elements(By.XPATH, '//*[@data-testid="cellInnerDiv"]')[i].click()

        sleep(3 + 4 * random())

        time_element = driver.find_element(By.TAG_NAME, "time")
        datetime_value = time_element.get_attribute("datetime")
        if datetime_value is not None:
            pubDate_datetime = datetime.fromisoformat(
                datetime_value[:-5]
            )  # Remove milliseconds for compatibility
        else:
            pubDate_datetime = None
        feed.add_item(
            title=driver.find_element(
                By.XPATH, '//*[@data-testid="tweetText"]'
            ).text.replace("\n", "")[:50]
            + "...",
            link=driver.current_url,
            description=driver.find_element(
                By.XPATH, '//*[@data-testid="tweetText"]'
            ).text,
            pubDate=pubDate_datetime,
        )
        sleep(3 + 4 * random())
    feed.export("docs/assets/rss/rss.xml")
except IndexError as e:
    print(e)
    feed.export("docs/assets/rss/rss.xml")
except Exception as e:
    print(e)
    feed.export("docs/assets/rss/rss.xml")
    driver.save_screenshot("something_wrong.png")
