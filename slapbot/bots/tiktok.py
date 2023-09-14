"""
Someone on a forum suggesting liking peoples tiktok comments was a way to increase engagement.
This is that bot, but it's not functional like you'd expect.
"""
import enum
import random
import time
import traceback

import click
from selenium.webdriver.common.by import By
from tqdm import tqdm

from slapbot import BrowserBotBase, DriverType
from slapbot import utils

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TikTokXpaths(enum.Enum):
    TAG_PAGE_HASHTAG_TITLE = "//h1[@data-e2e=\"challenge-title\"]"
    TAG_PAGE_HASHTAG_VIEW_COUNT = "//h2[@data-e2e=\"challenge-vvcount\" and @title=\"views\"]//strong"
    TAG_PAGE_VIDEO_LINK = "//div[@data-e2e=\"challenge-item\"]/div/div/a"
    VIDEO_PAGE_COMMENT_ITEM = '//*[@data-e2e="comment-like-count"]//parent::div//*[@fill="rgba(22, 24, 35, 1)"]'  # Only the unliked ones
    VIDEO_PAGE_COMMENT_COUNT_ELEMENT = "//p[contains(@class,\"e1a7v7ak1\")]"
    VIDEO_PAGE_VIEW_MORE_COMMENTS_ELEMENT = "//p[@data-e2e=\"view-more-1\"]"
    VIDEO_PAGE_VIEW_MORE_COMMENTS_ELEMENT_2 = "//p[@data-e2e=\"view-more-2\"]"


class TikTokBot(BrowserBotBase):
    def __init__(self, headless=None):
        super().__init__(driver_type=DriverType.FIREFOX, late_init=True,
                         headless=headless if headless is not None else False)

        self.attempt_to_center_scroll = True  # Scroll items into center of page.

        self.config = dict(
            # Terms that we'll be searching for to scrape videos from
            tags_to_scrape=[
                'hiphop',
                'rapper',
                'unsigned artist',
                'freestyle'
            ],
            # How many times to scroll down on the page (propagating new content)
            page_scroll_count=10,
            load_nested_comments=True,
            firefox_profile_path=self.locate_firefox_profile()
        )

    def startup(self):
        if not self.setup_complete:
            # Load (or create default & load) configuration for bot.
            self.config = utils.load_config(config_file_name="tiktok_config.json", default_config=self.config)

            # Initialize web driver
            if self.late_init is True:
                print(f"Initializing browser with profile @ {self.config['firefox_profile_path']}")
                self.init_driver(use_profile=True,
                                 profile_location=self.config['firefox_profile_path'])

            # Mark setup as complete.
            self.setup_complete = True
            print(f"Setup complete!")

    def begin(self):
        super().begin()

        self.debug("Beginning to parse tags for scraping")
        search_terms = self.config['tags_to_scrape']
        cli_bar = tqdm(search_terms)
        for search_term in cli_bar:
            self.driver.get(f'https://www.tiktok.com/tag/{search_term.replace(" ", "")}?lang=en')
            time.sleep(5)

            cli_bar.set_description(f"Retrieving hashtag title & viewcount on {search_term} | {self.driver.title}")
            # Title of the hashtag at the top of the page when viewing through 'discovery' feature.
            try:
                hashtag_title = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, TikTokXpaths.TAG_PAGE_HASHTAG_TITLE.value)
                    )
                )
            except:
                self.debug(
                    f"Unable to locate tag title for search term {search_term} @ {self.driver.current_url} | {self.driver.title}",
                    progress_bar=cli_bar)

                return

            try:
                hashtag_viewcount = WebDriverWait(self.driver, timeout=10).until(
                    EC.visibility_of_element_located(
                        (By.XPATH, TikTokXpaths.TAG_PAGE_HASHTAG_VIEW_COUNT.value)
                    )
                )
            except:
                self.debug(
                    f"Unable to locate hashtag video view count for {search_term} at {self.driver.current_url} | {self.driver.title}")
                return

            cli_bar.set_description(f"Loading page videos.")
            # Scroll down a bunch.
            self.send_keypress_to_page(count=random.randint(50, 100), sleep_time=0.2)

            # Retrieve all the video elements on the page.

            cli_bar.set_description(f"Processing page for videos")

            try:
                video_link_elements = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, TikTokXpaths.TAG_PAGE_VIDEO_LINK.value)
                    )
                )
            except:
                self.debug(
                    f"Failed to collect videos from search term: '{search_term}' @ {self.driver.current_url} | {self.driver.title}")
                return

            # Process elements to collect links.
            video_links = [e.get_attribute('href') for e in video_link_elements]
            self.debug(f"Found {len(video_links)} videos to use on hashtag {search_term}")

            video_link_progress_bar = tqdm(video_links)

            self.debug(f"-- Beginning to navigate videos from '{search_term}' search")

            for link in video_link_progress_bar:
                # Navigate to driver
                self.driver.get(link)
                time.sleep(10)

                try:
                    comment_count_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located(
                            (By.XPATH, TikTokXpaths.VIDEO_PAGE_COMMENT_COUNT_ELEMENT.value)
                        )
                    )
                except:
                    self.debug(
                        f"Unable to locate comment count on video page: {self.driver.current_url} | {self.driver.title}")
                    continue

                # Page loads 20 comments at a time, and this leaves us to figure out how much we need to scroll
                # to load all the pages content.
                video_link_progress_bar.set_description("Processing comment count")
                comment_count_text = comment_count_element.text
                comment_count = int(comment_count_text.split(' ')[0])
                comment_count = int(comment_count / 20) + 1

                # Scroll that many times before continueing.
                video_link_progress_bar.set_description("Loading video comments via page scroll")
                self.send_keypress_to_page(count=comment_count, sleep_time=0.4)

                # Optionally load all nested comments on the page too- Maximising results of reach.
                if self.config['load_nested_comments']:
                    # Now with all these elements loaded we're going to click the 'view more comments' buttons
                    # recursively until there are no more left.

                    # There are two layered buttons to show

                    video_link_progress_bar.set_description(
                        "Processing video page comment elements for more nested comments")
                    view_more_comments_elements = []
                    try:
                        view_more_comments_elements = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_all_elements_located(
                                (By.XPATH, TikTokXpaths.VIDEO_PAGE_VIEW_MORE_COMMENTS_ELEMENT.value)
                            )
                        )
                    except:
                        self.debug(f"Unable to find comments with nested replies on {self.driver.current_url}")
                        pass

                    if len(view_more_comments_elements) > 0:
                        # Ideally what we have done after this loop is all the comments & their (nested) replies loaded for parsing.
                        for view_more_button in view_more_comments_elements:
                            try:
                                self.debug("Scrolling element into view")
                                self.scroll_into_view(view_more_button)
                                time.sleep(2)
                                if not view_more_button.is_displayed():
                                    self.debug(f"Element {view_more_button} is not displayed on screen - Skipping",
                                               progress_bar=video_link_progress_bar)
                                    continue

                                view_more_button.click()
                                time.sleep(0.3)
                            except Exception as ex:
                                self.debug(
                                    f"Error when performing 'View more comments' on {self.driver.current_url} | {self.driver.title}")
                                traceback.print_exc()
                                pass

                            still_loading_comments = True
                            while still_loading_comments:
                                try:
                                    view_more_comment_elements_second_iteration = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_all_elements_located(
                                            (By.XPATH, TikTokXpaths.VIDEO_PAGE_VIEW_MORE_COMMENTS_ELEMENT_2.value)
                                        )
                                    )
                                except Exception as ex:
                                    self.debug(
                                        f"Error when loading more comments on {self.driver.current_url} | {self.driver.title}")
                                    traceback.print_exc()
                                    break

                                view_more_iteration_count = 0
                                for element in view_more_comment_elements_second_iteration:
                                    try:
                                        if not element.is_displayed():
                                            continue
                                        self.scroll_into_view(element)
                                        time.sleep(0.2)
                                        element.click()
                                    except Exception as ex:
                                        self.debug(
                                            f"Error when loading nested comments [Iter # {view_more_iteration_count}] on {self.driver.current_url} | {self.driver.title}")
                                        still_loading_comments = False
                                        break

                                    view_more_iteration_count += 1

                                still_loading_comments = False

                # Now we load the comment like buttons & start slapping the shit outta em'
                try:
                    comment_like_buttons = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.XPATH, TikTokXpaths.VIDEO_PAGE_COMMENT_ITEM.value))
                    )
                except Exception as ex:
                    self.debug("Error when loading comment like buttons")
                    traceback.print_exc()
                    continue

                self.debug("Comment like progress")
                button_progress_bar = tqdm(comment_like_buttons)
                clicked_count = 0
                total_amount_to_click = len(comment_like_buttons)
                for button in button_progress_bar:
                    try:
                        self.scroll_into_view(button)
                        if not button.is_displayed():
                            self.debug(f"Expected button @ {button} is not displayed. Skipping.",
                                       progress_bar=button_progress_bar)
                            continue
                        button.click()
                        clicked_count += 1
                        button_progress_bar.set_description(
                            f"[{clicked_count}/{total_amount_to_click}] Clicked! Sleeping")
                    except Exception as ex:
                        self.debug(
                            f"Error when clicking comment button on {self.driver.title} @ {self.driver.current_url}")


@click.group()
def cli():
    pass


@cli.command("reach")
@click.option('--headless', is_flag=True, default=False, help="Run the browser headless?")
def reach(headless):
    bot = TikTokBot(headless=headless)
    bot.begin()


if __name__ == "__main__":
    cli()
