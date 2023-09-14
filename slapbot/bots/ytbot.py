import json
import random
import time
import traceback
import urllib.request as req

import click
from dotmap import DotMap
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from slapbot import utils
from slapbot.bots import BrowserBotBase, DriverType
from slapbot.models import YoutubeChannel, YoutubeVideoComment, ActionLog

"""
BOT LOGIC
        # Select a query
        # Perform said query
        # Scroll through page and parse html along the way for video links

        # Begin loop through collected query links.
        # check if link has been commented on previously (log check)
        # visit link
        # navigate to comment section
        # verify if comment section is able to be posted on
        # post (if possible) or skip & log to file
        # continue in loop
"""


# //*[@id="date"]/yt-formatted-string
# Check if "Premier" in text

class Endpoints:
    BASE_URL = "https://www.youtube.com{0}"
    SEARCH_RESULTS = "https://www.youtube.com/results?search_query={0}&sp={1}"  # get results for today.


class AuthorNotFoundException(BaseException):
    """
    Thrown when author element is not
    found on the video page
    """
    pass


class RecentlyCommentedException(BaseException):
    """
    Thrown when a comment has been posted recently on the channel, and the bot
    is waiting for the cooldown time to pass before posting again on this channel
    """
    pass


class VideoInPremiereException(BaseException):
    """
    Thrown when a video is in premiere mode,
    and the bot is waiting for the video to be released
    """
    pass


def has_commented_on(url):
    """
    Whether or not we've commented on this video before.
    """
    comment: YoutubeVideoComment = YoutubeVideoComment.query.filter_by(url=url).first()
    return comment is not None


class YoutubeBot(BrowserBotBase):
    """
    YoutubeBot is a bot that will search for videos based on a query, and comment on them.
    """

    def __init__(self, **kwargs):
        super().__init__(driver_type=DriverType.FIREFOX, headless=False)

        self.config_file_name = "ytbot_config.json"

        self._config = dict(
            wait_times=dict(  # how long to wait between posting another comment on videos
                comment_wait_hours=12,  # 12 hours
                comment_wait_days=4  # 4 days
            ),
            subscribe=dict(  # subscribe to the channel of the video
                enabled=True,  # whether or not to subscribe to the channel
                chance=100  # chance to subscribe to the channel
            ),
            like={  # like the video
                'enabled': True,  # whether or not to like the video
                'chance': 100  # chance to like the video
            },
            search_option="EgIIAQ%253D%253D",  # search option for youtube
            wait_time_min=20,  # minimum wait time between actions
            wait_time_max=25,  # maximum wait time between actions
            video_search_limit=50,  # how many videos to search for
            firefox_profile_path=self.locate_firefox_profile() if not None else "none",
            # path to firefox profile (auto-located)
            restart_when_finished=True,  # whether or not to restart the bot when finished
            title_restriction=True,  # whether or not to filter out videos with the below title_filter in the title
            title_filter="type beat",  # filter out videos with this in the title
            restart_cooldown_time=4800,  # Restart cooldown time in seconds
            restart_cooldown_time_min=100,  # Restart cooldown time minimum
            restart_cooldown_time_max=200,  # Restart cooldown time maximum
            scroll_pixels=700,  # How far the page the bot should scroll down
            wait_days_between_channel_comment=3,  # How many days to wait before commenting on the same channel
            maximum_waits=5,  # Maximum number of times to wait for a page to load
            unsubscribe_all=False,
            queries=[  # Queries to search for
                "biggie smalls type beat",  # query
            ],
            comments=[  # Comments to post
                "[compliment] {[smiley-face]|}"
            ],
            descriptive_tags={  # Descriptive tags to use in comments
                "smiley-face": [
                    "🔥"
                ],
                "compliment": [
                    "[smiley-face] {Tap in with me|Tap in|Lets cook|You open to collab?|HMU for a collab|||}",
                ],

            }
        )

    def can_post_on_channel(self, url):
        """
        Whether or not we've posted on this channel recently.
        Posting on channels to frequently can cause issues in the community.
        """
        channel: YoutubeChannel = YoutubeChannel.query.filter_by(url=url).first()

        if channel is None:
            return True

        return not channel.has_commented_recently(days=self.config['wait_times']['comment_wait_days'],
                                                  hours=self.config['wait_times']['comment_wait_hours'])

    def subscribe_to_channel(self, video_url) -> bool:
        """Subscribe to the channel of the video."""
        if not self.driver.current_url == video_url:
            self.driver.get(video_url)
            time.sleep(0.5)

        try:
            subscribe_button = WebDriverWait(self.driver, timeout=10).until(
                EC.presence_of_element_located((By.XPATH, '//button[contains(@aria-label,"Subscribe")]'))
            )
            self.scroll_into_view(subscribe_button, center=True)
            subscribe_button.click()
        except:
            return False

    def like_video(self, url: str, comment_obj: YoutubeVideoComment) -> bool:
        """Like the video"""
        if not self.driver.current_url == url:
            self.driver.get(url)
            time.sleep(0.5)
            self.scroll_with_javascript(700)

        # todo implement chance
        try:
            like_button = WebDriverWait(self.driver, timeout=10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@id="actions-inner"]//div[@id="segmented-like-button"]//button'))
            )
            self.scroll_into_view(like_button, center=True)

            aria_label_text = like_button.get_attribute("aria-label")

            if "like" in aria_label_text:
                like_button.click()
                comment_obj.liked = True
                comment_obj.save(commit=True)

            return True
        except:
            return False

    def scrape_video_information(self, url) -> DotMap | None:
        """
        Scrape video information from the video page.
        :param url: The url of the video page.
        :return: A dictionary of video information, or none if not found.

        Format:
            {
                'title': 'Video Title',
                'author': 'Author Name',
                'author_url': 'https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxx',
                'views': 123456,
            }
        """
        if not self.driver.current_url == url:
            try:
                self.driver.get(url)
                time.sleep(round(random.uniform(0.0, 2.5), 2))
            except:
                traceback.print_exc()
                return None

        try:
            video_unavailable = WebDriverWait(self.driver, timeout=5).until(
                EC.visibility_of_element_located((By.XPATH, '//div[contains(text(),"Video unavailable")]'))
            )
            self.debug("Video unavailable at {0}".format(url))
            return None
        except:
            pass

            # Scroll page down with key press & atempt to load comment box.

            self.driver.execute_script("window.scrollBy(0, 700);")

        # Retrieve author (uploader) name via element xpath
        try:
            author_element = WebDriverWait(self.driver, timeout=5, poll_frequency=2).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="text"]/a[1]')),
                f'Unable to locate author element on {url}'
            )
            author_name = author_element.text
            author_url = author_element.get_attribute('href')
            if author_name is None or len(author_name) == 0:
                self.debug("Unable to locate author name on page {0}".format(author_url))
                author_name = "Unknown"

            self.debug('Author of video at {0} is {1}'.format(author_url, author_name))
        except Exception as e:
            raise AuthorNotFoundException(f"Unable to locate author element on video {url}")

        self.debug(f"Checking if we can post on {url}")

        if not self.can_post_on_channel(author_url):
            self.debug(
                f"Posted on {author_name} videos in the last {self.config['wait_times']['comment_wait_days']} days.")
            raise RecentlyCommentedException(
                f"Posted on {author_name} videos in the last {self.config['wait_times']['comment_wait_days']} days.")

        self.debug("Checking for premiered video type")
        try:
            uploaded_element = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="info-container"]/yt-formatted-string'))
            )

            if 'Premiers' in uploaded_element.text:
                self.debug("Skipping premiering / premiered video")
                return None
        except:
            pass

        # View count variable
        view_count = "No Video Selected"
        video_title = "No Video Selected"
        self.debug("Collecting view count & video title")
        try:
            view_count_element = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="info"]/span[contains(text(),"views")]'))
            )
            view_count = view_count_element.text
            view_count = view_count.split(' ')[0]

        except Exception as e:

            if self.check_xpath_exists('//*[@id="chat-messages"]/yt-live-chat-header-renderer'):
                self.debug("Found a premier~ Skipping- Its not live rn.")
                return None

            self.debug("Unable to locate viewcount; Likely premiering.")

        try:
            video_title_element = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="title"]/h1/yt-formatted-string'))
            )
            # video_title_element = self.driver.find_element_by_xpath('//*[@id="container"]/h1/yt-formatted-string')
            video_title = video_title_element.text
            if self.config['title_restriction'] and self.config['title_filter'] not in video_title.lower():
                self.debug(
                    f"Video {video_title} doesn't match filter {self.config['title_filter']}")
                return None

            self.debug(f"Video {video_title} ({url}) Uploaded by {author_name} w/ {view_count} views")

        except Exception as e:
            self.debug("Unable to video title")

        return DotMap(title=video_title, author=author_name, author_url=author_url, views=view_count)

    def begin(self):
        """
        Will query youtube (search) to collect videos that we can comment on.
        Traverses these urls, checks if we've commented on this users channel recently (to avoid spam) and
        if we're all good it loads the video & posts a comment after some time.
        """

        if not self.setup_complete:
            self.startup(config_file_name="ytbot_config.json", driver_type=self.driver_type)
            self.setup_complete = True

        self.progress_bar = tqdm()

        if self.requires_login():
            click.secho("Login required", fg="red")
            input("Press enter to continue...")
            return

        while True:
            # self.debug(f"~ Checking for collected video urls")
            # collected_urls = ActionLog.get("ytbot_collected_urls", []).value
            # original_count = len(collected_urls)

            # if len(collected_urls) == 0:
            self.debug(f"~ Querying youtube")
            # collected_urls_stored = json.loads(ActionLog.get("ytbot_collected_urls", default_value=[]).value)
            # if not isinstance(collected_urls_stored, list):
            #     raise Exception(
            #         f"Error decoding collected urls stored from database: {collected_urls_stored.value} | {type(collected_urls_stored.value)}")
            #
            # if len(collected_urls_stored) > 0:
            #     collected_urls = collected_urls_stored
            # else:

            if self.config['unsubscribe_all'] is True:
                self.debug("Unsubscribing from all channels")
                self.unsubscribe_from_all_channels()

            collected_urls = self._query_and_collect_urls()
            ActionLog.log("ytbot_collected_urls", collected_urls)

            collected_urls = [url for url in collected_urls if not has_commented_on(url=url)]

            random.shuffle(collected_urls)
            self.debug("~ Starting Comment Sequence")

            for url in collected_urls:

                if has_commented_on(url):
                    self.debug("Skipping duplicate comment on video: %s" % url)
                    continue

                self.debug(f"Scraping video information: {url}")

                # Get the video information in a dotmap
                try:
                    video_info = self.scrape_video_information(url=url)
                except:
                    continue

                if video_info is None:
                    self.debug(f"Skipping video: {url}")
                    continue

                try:
                    if self.check_xpath_exists('//span[contains(text(),"Comments are")]'):
                        self.debug(
                            f"Comments are disabled on '{video_info['title']} by {video_info.author} @ {url} ")
                        continue
                except:
                    continue

                try:
                    comment_box = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH,
                                                        "//ytd-comment-simplebox-renderer[@class='style-scope ytd-comments-header-renderer']")))
                except:
                    self.debug("Comments likely disabled.")
                    continue

                ##
                # BEGIN COMMENTING
                ##

                try:
                    # activate the comment box.
                    comment_box_placeholder_area = WebDriverWait(self.driver, timeout=10).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="placeholder-area"]'))
                    )
                    self.scroll_into_view(comment_box_placeholder_area, center=True)
                    time.sleep(random.randint(1, 3))
                    comment_box_placeholder_area.click()
                    self.debug("Clicking comment box placeholder")

                except Exception as e:
                    traceback.print_exc()
                    self.debug("Cannot find comment box")
                    print("Cannot find comment box")
                    continue

                try:  # move to the comment box
                    comment_box = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="contenteditable-root"]')))
                except:
                    pass
                # Generate a comment with placeholders
                try:
                    self.debug("* Generator performing comment operations *")
                    comment = utils.generate_comment_using_spintax(text=random.choice(self.config['comments']),
                                                                   tags_to_query=self.config['descriptive_tags'],
                                                                   author_name=video_info['author'])
                    self.debug(f"* Comment Generated: {comment}")
                except Exception as e:
                    self.debug(f'Error generating comment: {e}')
                    continue

                self.debug("Beginning to post comment")
                try:

                    comment_box.send_keys(comment)
                    bot_sleep_time = random.randint(1, 15)
                    self.debug(f"Comment written- Sleeping {bot_sleep_time}s to avoid bot banning")
                    time.sleep(random.randint(1, 15))

                    comment_button = WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@aria-label="Comment"]'))
                    )
                    comment_button.click()

                    # todo like & subscribe

                    self.push_log(video_info['author_url'], video_info['author'], video_info['title'], url, comment)

                    try:
                        if self.config['like']['enabled'] and self.config['like']['chance'] >= random.randint(1, 100):
                            self.debug("Liking video")
                            self.like_video(url=url, comment_obj=YoutubeVideoComment.query.filter_by(url=url).first())

                        if self.config['subscribe']['enabled'] and self.config['subscribe']['chance'] >= random.randint(
                                1, 100):
                            self.debug("Subscribing to channel")
                            self.subscribe_to_channel(video_url=url)
                    except:
                        traceback.print_exc()

                    wait_time = random.randrange(self.config['wait_time_min'], self.config['wait_time_max'])
                    self.debug(f"Comment Posted on {video_info.title} ~ Waiting {wait_time}s before next comment")
                    time.sleep(wait_time)
                except Exception as ex:
                    print(ex)
                    self.debug("Unable to post comment on video.. Skippping")

            ActionLog.log("ytbot_collected_urls", [])

    def push_log(self, author_url, author_name, video_title, url, comment):
        """
        Push record of posting on a video, channel,and comment to the database for future reference.
        """

        channel = YoutubeChannel.get_or_create(url=author_url, name=author_name)

        if channel is None:
            channel = YoutubeChannel.create(url=author_url, name=author_name)

        video_comment = YoutubeVideoComment(channel=channel, url=url, message=comment)
        video_comment.save(commit=True)

    def requires_login(self):
        """Check whether or not the 'Sign in' button is present on the page."""
        try:
            login_button = WebDriverWait(self.driver, timeout=5).until(
                EC.presence_of_element_located((By.XPATH, '//a[@aria-label="Sign in"]'))
            )
            return True
        except:
            return False

    def _query_and_collect_urls(self):
        """
        Perform search queries & collect the scraped videos from these queries.
        """

        # Iterate each query that's to be looped.
        collected_videos = []
        queries = self.config['queries']
        self.debug(f"Shuffling array of {len(queries)} queries")
        random.shuffle(queries)
        query = random.choice(queries)

        log = ActionLog.get(f"ytbot_search_query_{query}", [])

        # if log.last_updated_within_hopurs(1):
        #     self.debug(f"Query '{query}' was last performed within the last hour. Skipping.")
        #     return self._query_and_collect_urls()

        items = json.loads(log.value)

        _remaining_items_to_comment = []
        if len(items) >= 0:
            for item in items:
                if has_commented_on(item):
                    continue
                _remaining_items_to_comment.append(item)

            if len(_remaining_items_to_comment) >= 1:
                random.shuffle(_remaining_items_to_comment)
                return _remaining_items_to_comment

        try:
            self.debug(f"Performing search for '{query}'")
            self.do_search(query)
        except Exception as e:
            traceback.print_exc()

        try:
            # This is the part where we scroll to the bottom of the feed.
            bottom_of_page = False

            while not bottom_of_page:
                for vid in self._collect_videos_from_loaded_search():
                    if vid not in collected_videos:
                        collected_videos.append(vid)

                    if len(collected_videos) >= self.config['video_search_limit']:
                        self.debug("Video Search Limit Reached (%s/%s)".format(len(collected_videos),
                                                                               self.config[
                                                                                   'video_search_limit']))
                        bottom_of_page = True
                        break

                # No results on search page.
                # if self.check_xpath_exists('//*[@id="contents"]//div[@id="dismissable" and contains(@class,"ytd-video-renderer")]'):
                try:
                    no_more_results = WebDriverWait(self.driver, 1).until(EC.visibility_of_element_located(
                        (By.XPATH, '//*[@id="message" and contains(text(),"No more results")]')
                    ))
                    self.debug("No more results found.")
                    break
                except:
                    pass

                if self.check_xpath_exists('//*[contains(text(),"No results found")]'):
                    self.debug("No results on search page")
                    break

                try:
                    # print("Looking for 'No more results' msg")
                    element = WebDriverWait(self.driver, 1).until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="message"]'))
                    )

                    if "No more results" in element.text:
                        bottom_of_page = True
                        for vid in self._collect_videos_from_loaded_search():
                            if vid not in collected_videos:
                                collected_videos.append(vid)
                        break
                except Exception as ex:
                    pass
                self.driver.execute_script("window.scrollBy(0, 700);")
                self.debug("Scrolling to bottom of page to load more videos")

        except Exception as ex:
            print(ex)
            print("^------ Error iterating queries")

        self.debug(f"Collected {len(collected_videos)} from scraping.")
        ActionLog.log(f"ytbot_search_query_{query}", collected_videos)
        return collected_videos

    def do_search(self, search_term):
        """
        Perform a search for the given terms.
        """
        try:
            self.driver.get(
                Endpoints.SEARCH_RESULTS.format(req.pathname2url(search_term), self.config['search_option']))
            self.driver.implicitly_wait(5)
            time.sleep(3)
        except Exception as e:
            print(f"Unable to navigate to: {search_term}")
            traceback.print_exc()

    def _collect_videos_from_loaded_search(self):
        """
        Expects that it's on a youtube search page URL. Will collect the videos loaded from this search,
        parse out google ads & premiers, and then return these urls for us to comment on later.
        """
        _v = []

        try:
            video_elements = WebDriverWait(self.driver, 5).until(
                EC.presence_of_all_elements_located((By.XPATH,
                                                     '//a[@id="thumbnail" and contains(@class,"yt-simple-endpoint inline-block style-scope ytd-thumbnail") and contains(@href,"watch") or contains(@href,"shorts")]'))
            )
        except Exception as e:
            traceback.print_exc()
            return _v

        self.debug(f"Processing {len(video_elements)} videos from search page...", println=True)

        if not video_elements or video_elements is None:
            return _v

        def filtered_video(url):
            return 'googlead' in url or 'premiere' in url

        for video in video_elements:
            try:
                video_url = video.get_attribute("href")

                if video_url is None:
                    self.debug("Another element without href")
                    continue

                if "shorts" in video_url:
                    video_url = video_url.replace("shorts/", "watch?v=")

                if video_url not in _v and not filtered_video(video_url):
                    _v.append(video_url)
                    # print(f'+ {href}')
            except Exception as e:
                traceback.print_exc()
                continue

        return _v
