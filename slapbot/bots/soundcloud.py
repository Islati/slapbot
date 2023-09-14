import datetime
import json
import random
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from slapbot.bots import BrowserBotBase, DriverType
from slapbot.models import SoundcloudLike, SoundcloudComment, SoundcloudUser


class SoundcloudBot(BrowserBotBase):
    def __init__(self):
        super().__init__()

        self._config = dict(
            firefox_profile_path=self.locate_firefox_profile(),
            chrome_profile_path=self.locate_chrome_profile(),
            wait_time_min=40,
            wait_time_max=120,
            comment_wait_time_min=3,
            comment_wait_time_max=30,
            chance_of_comment=10,
            chance_of_like=30,
            commenting=False,
            like_tracks=True,
            base_url="https://soundcloud.com/search/sounds?q={0}&filter.created_at={1}",
            search_queries=[
                "type beat"
            ],
            search_filter="last_hour",
            comments=[
                '[author] {Tap in|HMU|Check in|Lets work}- {I like|I love|Love} your {sound|style|music} [smiley-face] [final_words]',
                '[smiley-face] [author]'
            ],
            descriptive_tags={
                'exciting-punctuation': [
                    '!', '!!'
                ],
                "final_words": [
                    "Bless {up|}",
                    "Cheers{!|}",
                    "Stay {blessed|motivated|focused|true}{!|.}",
                    "Much love{!|.}"
                ],
            }
        )
        self.config_file_name = "scbot_config.json"

        self.closed_popup_modal = False

    def has_commented_on_track(self, url):
        return SoundcloudComment.query.filter_by(url=url).first() is not None

    def has_liked_track(self, url):
        """
        Check if we have liked the track already.
        """

        return SoundcloudLike.query.filter_by(url=url).first() is not None

    def has_posted_comment_in_past_days_on_profile(self, url, days=5):
        """
        Used to check if we can comment on any of the authors links...
        It's proven that users don't like receiving multiple messages about the same thing.
        """

        comments = SoundcloudComment.query.filter_by(url=url).all()
        if not comments:
            return False

        for comment in comments:
            # If the date range is in the recent days
            if (datetime.datetime.utcnow() - comment.created_at).days < days:
                return True

        return False

    def collect_author_urls(self):
        """
        Collect the authors profile links. Used in the business logic post page load of a search term.
        """
        author_link_xpath = '//*[@id="content"]/div/div/div[3]/div/div/div/ul/li/div/div/div/div[2]/div[1]/div/div/div[2]/div/a'

        author_links = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_all_elements_located((By.XPATH, author_link_xpath))
        )

        links = []
        count = 0
        for link_element in author_links:
            count += 1
            href = link_element.get_attribute('href')
            if href in links:
                continue

            links.append(href)

        return links

    def get_random_wait_time(self):
        return random.randint(self.config['wait_time_min'], self.config['wait_time_max'])

    def get_random_comment_wait_time(self):
        return random.randint(self.config['comment_wait_time_min'], self.config['comment_wait_time_max'])

    def check_and_close_ad_popup(self):
        """
        Close the modal that pops up promoting soundcloud services to soundcloud users (If it exists on the DOM).
        """
        try:
            popup_modal = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@class,'js-inAppModal__close')"))
            )
            popup_modal.click()
            self.closed_popup_modal = True
        except Exception as e:
            return

    def begin(self):
        self.startup(config_file_name="../../soundcloud_config.json", driver_type=DriverType.CHROME)

        print("Beginning search logic")

        search_url_base = self.config['base_url']

        search_queries = self.config['search_queries']
        if len(search_queries) == 0:
            print("No search queries")
            exit(-9)
            return

        print(f"Search queries [{json.dumps(search_queries)}]")

        for search_query in search_queries:
            # Navigate the search term.
            search_url = search_url_base.format(search_query, self.config['search_filter'].replace(" ", "%20"))
            print(f"Attempting to navigate to {search_url}")
            self.driver.get(search_url)
            print('Waiting 5s')
            time.sleep(5)
            input("Press enter to continue")

            # Perform scrolling to the bottom of the page (atleast, perceived bottom).
            author_urls = []
            print("Scrolling to propogate content")
            for i in tqdm(range(random.randint(self.config['scroll_min'], self.config['scroll_max']))):
                self.send_keypress_to_page()
                time.sleep(1)

                previous_length = len(author_urls)
                try:
                    author_urls = self.collect_author_urls()
                except Exception as e:
                    print(e)
                    self.check_and_close_ad_popup()

                new_length = len(author_urls)

                if previous_length == new_length:
                    break

            progress_bar = tqdm(author_urls)
            for author_profile_url in progress_bar:  # Iterate through all users

                commented = False
                liked = False

                tracks_url = author_profile_url + "/tracks"
                self.driver.get(tracks_url)  # goto the tracks page (just cause there is more info)

                time.sleep(random.randint(2, 5))

                try:
                    author_name = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//*[contains(@class,'profileHeaderInfo__userName')]"))
                    ).text

                    if ' ' in author_name:
                        author_name = author_name.split(' ')[0]

                    if '|' in author_name:
                        author_name = author_name.split('|')[0]

                    progress_bar.set_description(f"Found author name {author_name}")
                except Exception as e:
                    traceback.print_exc()
                    print(f"Cannot find author name @ {author_profile_url}")
                    input(f"Press enter to continue.")
                    continue

                # Hack method to load some more on the page!!

                no_tracks = False

                for i in range(random.randint(1, 2), random.randint(3, 5)):
                    self.send_keypress_to_page()
                    if random.randint(1, 100) >= 20:
                        break
                    time.sleep(random.randint(1, 4))

                track_info = []
                try:
                    # recent_tracks = self.driver.find_elements_by_xpath("//a[contains(@class,'soundTitle__title')]")
                    recent_upload_list = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class,'sound__body')]"))
                    )

                except:
                    print("Unable to locate recent tracks (sound__body elements)")
                    continue

                print(f"Found {len(recent_upload_list)} recent uploads")

                for track in recent_upload_list:

                    # Get the track link.
                    try:
                        track_link_element = track.find_element("xpath","//a[contains(@class,'soundTitle__title')]")
                    except:
                        traceback.print_exc()
                        print(f"Unable to locate link element for track on profile {author_profile_url}")
                        break

                    try:
                        track_link = track_link_element.get_attribute('href')
                    except:
                        traceback.print_exc()
                        print(f"Unable to locate track link")
                        continue

                    try:
                        track_title = track_link_element.find_element(by=By.TAG_NAME,value='span').text
                    except:
                        traceback.print_exc()
                        print(f"Unable to locate track title")
                        continue

                    try:
                        play_button = track.find_element(by=By.XPATH,value=
                            "//div[contains(@class,'sound__header')]/div/div/div[contains(@class,'soundTitle__playButton')]/a")
                    except:
                        print(f"Unable to locate play button.")
                        continue

                    play_button_clicked = False

                    # Commenting Logic
                    if self.config['commenting'] is True and random.randint(0, 100) <= self.config[
                        'chance_of_comment']:
                        # Check if we can post on the users profile.
                        if not self.has_posted_comment_in_past_days_on_profile(author_profile_url, days=10):
                            progress_bar.set_description(f"Recently commented on profile @ {author_profile_url}")
                            break

                        progress_bar.set_description(f"Evaluating logic comment for {track_title}")

                        if self.has_commented_on_track(track_link):
                            progress_bar.set_description(
                                f"Skipping {track_title} and author {author_name}: Contains Comment Already (Recent).")
                            break

                        time_to_wait = self.get_random_comment_wait_time()
                        try:
                            play_button.click()
                        except:
                            print(f"Unable to click play button")
                            continue
                        play_button_clicked = True
                        progress_bar.set_description(f"Waiting {time_to_wait}s before commenting on track")
                        time.sleep(time_to_wait)

                        try:
                            comment_input_box = track.find_element(by=By.XPATH,value=
                                "//input[contains(@class,'commentForm__input')]")

                        except:
                            print(f"Unable to locate comment box on track {track_title}")
                            traceback.print_exc()
                            input("Press enter to continue")
                            continue

                        comment = self.generate_comment_from_spintax(author_name=author_name)

                        if len(comment) <= 0:
                            progress_bar.set_description(f"Generated an empty comment")
                            continue
                        comment_input_box.send_keys(comment)
                        comment_input_box.send_keys(Keys.ENTER)
                        commented = True
                        self.push_comment_log(author=author_name, author_url=author_profile_url, url=track_link,
                                              comment=comment)
                        time.sleep(random.randint(1, 3))

                    # Like track logic
                    if self.config['like_tracks'] and random.randint(0, 100) <= self.config['chance_of_like']:
                        if self.has_liked_track(track_link):
                            progress_bar.set_description(f"Skipping {author_profile_url} as it's already liked")
                            continue

                        if not play_button_clicked:
                            time_to_wait = self.get_random_comment_wait_time()
                            try:
                                play_button.click()
                            except:
                                traceback.print_exc()
                                continue
                            play_button_clicked = True
                            progress_bar.set_description(f"Waiting {time_to_wait}s before like the track")
                            time.sleep(time_to_wait)

                        try:
                            like_button = track.find_element(by=By.XPATH,value="//button[contains(@class,'sc-button-like')]")
                        except:
                            traceback.print_exc()
                            continue
                        time.sleep(0.5)

                        try:
                            like_button.click()
                        except:
                            traceback.print_exc()
                            continue
                        liked = True
                        self.push_like_log(author=author_name, author_url=author_profile_url, url=track_link)
                        time.sleep(random.randint(1, 3))

                if commented or liked:
                    sleep_time = self.get_random_wait_time()
                    progress_bar.set_description(f"Sleeping for {sleep_time}s before the next action!")
                    time.sleep(sleep_time)

    def push_comment_log(self, author, author_url, url, comment):
        user = SoundcloudUser.get_or_create(url=author_url, name=author)

        comment = SoundcloudComment(user=user, url=url, comment=comment)
        comment.save(commit=True)

    def push_like_log(self, author, author_url, url):
        user = SoundcloudUser.get_or_create(url=author_url, name=author)
        like = SoundcloudLike(user=user, url=url)
        like.save(commit=True)

import click
from slapbot import create_app
from slapbot.config import Config

flask_app = create_app(Config())
bot = None

if __name__ == "__main__":
    sc_bot = SoundcloudBot()
    while True:
        sc_bot.begin()
        refresh_time = sc_bot.get_random_wait_time() * random.randint(3, 4)
        print(f"Sleeping for {refresh_time}s before next search iteration.")
        time.sleep(refresh_time)
