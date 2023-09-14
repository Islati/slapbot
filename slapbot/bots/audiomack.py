import datetime
import random
import time

from selenium.webdriver.support.wait import WebDriverWait

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from slapbot.bots import BrowserBotBase, Interaction, DriverType


class Xpaths(object):
    PAGE_BODY_LOADED = "//body[contains(@class,'is-logged-in') and contains(@class,'has-active-player']"
    RECENTLY_ADDED_PAGE_SONG_CONTAINER = "//div[contains(@class,'music-detail-container')]"
    RECENTLY_ADDED_PAGE_SONG_LINK = "//div[contains(@class,'music-detail-container')]//a[contains(@class,'music-detail__link')]"
    RECENTLY_ADDED_PAGE_ARTIST_LINKS = "//div[contains(@class,'music-detail-container')]//ul[contains(@class,'music__meta')]//a[@tabindex='0' and not(contains(@class,'music-detail__tag'))]"
    USER_PROFILE_FEED_SONG_CONTAINER = "//div[contains(@class,'music-detail--song') and contains(@class,'user-profile__feed-item')]"
    USER_PROFILE_SONG_LINK = "//div[contains(@class,'music-detail--song') and contains(@class,'user-profile__feed-item')]//a[contains(@class,'music-detail__link')]"
    USER_PROFILE_LIKE_TRACK = "//ul[contains(@class,'music__meta')]//button[@data-action='favorite']"
    USER_PROFILE_ARTIST_NAME = "//h1[@class='user-profile__name']"
    SONG_LINK_PLAY_BUTTON = "//button[contains(@class,'play-button') and not(contains(@class,'player__control'))]"
    SONG_LINK_SONG_DURATION_TEXT = "//div[contains(@class,'music-detail-container')]//span[contains(@class,'waveform__time') and contains(@class,'waveform__duration')]"
    SONG_LINK_COMMENT_BOX = "//div[@id='comments']//textarea[contains(@name,'comment_content')]"
    SONG_LINK_POST_COMMENT_BUTTON = "//div[@id='comments']//button"


class AudioMackBot(BrowserBotBase):
    def __init__(self):
        super().__init__(driver_type=DriverType.FIREFOX)

        self.like_log_file_name = "audiomack_like_log.json"
        self.comment_log_file_name = "audiomack_comment_log.json"
        self.repost_file_name = "audiomack_repost_log.json"
        self.config_file_name = "audiomack_config.json"
        self.play_log_file_name = "audiomack_play_log.json"

        self.config = dict(
            wait_time_min=60,
            wait_time_max=360,
            comment_wait_time_min=15,
            comment_wait_time_max=120,
            like_wait_time_min=5,
            like_wait_time_max=15,
            chance_of_comment=75,
            chance_of_like=80,
            play_time_min=1,
            play_time_max=40,
            comment_write_post_wait_time_min=2,
            comment_write_post_wait_time_max=8,
            page_load_wait_time_min=8,
            page_load_wait_time_max=12,
            commenting=True,
            like_tracks=True,
            repost_tracks=False,
            base_url="https://audiomack.com/rap/recent",
            search_queries=[
                "type beat"
            ],
            comments=[
                ''
            ],
            descriptive_tags={
                'address-author': [
                    '{hey|heyyo|ayy|yo} [author]',
                    '[author]',
                    'hey'
                ],
                'exciting-punctuation': [
                    '!', '!!'
                ],
                'content-compliment': [
                    'You have {skills|talent}{, [address-author]|}'
                ],
                "final_words": [
                    "Bless {up|}",
                    "Cheers{!|}",
                    "Stay {blessed|motivated|focused|true}{!|.}",
                    "Much love{!|.}"
                ],
            }
        )

        self.closed_popup_modal = False

        self.comment_log = []
        self.like_log = []
        self.repost_log = []

        self.play_log = []

        self.author_log = {}

    def startup(self):
        if not self.setup_complete:
            # Load the configuration
            self.load_config(self.config_file_name)
            self.debug(f"+ Loaded {self.config_file_name}")

            if self.config['like_tracks'] is False and self.config['commenting'] is False and self.config[
                'repost_tracks'] is False:
                self.debug("Please enable one logic feature, such as like_tracks or commenting")

            # Load the comment log
            self.comment_log = self.load_json_file(self.comment_log_file_name)

            # Load the like log
            self.like_log = self.load_json_file(self.like_log_file_name)

            self.play_log = self.load_json_file(self.play_log_file_name)

            self.debug("Updating author data from log file")
            self._process_logs_for_author_log()
            self.debug(f".. Finished processing {len(self.author_log)} Items")

            self.setup_complete = True
            self.debug("Setup complete!")

    def _process_logs_for_author_log(self):
        """
        Create a key-value dictionary that holds user profiles, and the last time we had an action with them.
        """
        # Iterate the comment log.
        logs = []

        if self.comment_log is not None and len(self.comment_log) > 0:
            for item in self.comment_log:
                logs.append(item)

        if self.like_log is not None and len(self.like_log) > 0:
            for item in self.like_log:
                logs.append(item)

        if self.repost_log is not None and len(self.repost_log) > 0:
            for item in self.repost_log:
                logs.append(item)

        for log in logs:

            author_url = log['author-url']
            print(author_url)

            interaction_type = None

            if "comment" in log.keys():
                interaction_type = Interaction.COMMENT

            elif "like" in log.keys():
                interaction_type = Interaction.LIKE
            elif "repost" in log.keys():
                interaction_type = Interaction.REPOST
            elif "play" in log.keys():
                interaction_type = Interaction.PLAY

            if interaction_type is None:
                self.debug(f"Unable to locate interaction type on log entry {log}")
                continue

            if author_url in self.author_log.keys():
                url_timestamp = log['timestamp']
                timestamp = self.author_log[author_url]['timestamp']

                if url_timestamp > timestamp:  # update the timestamp on hand.
                    self.author_log[author_url] = {"timestamp": url_timestamp, "type": interaction_type}

            else:
                self.author_log[author_url] = {'timestamp': log['timestamp'], 'type': interaction_type}

    def _update_author_log(self, author_url, interaction_type):
        self.author_log[author_url] = {'timestamp': time.time(), 'type': interaction_type}

    def push_like_log(self, author, author_url, url):
        """
        Push an object to the like log.
        """
        timestamp = time.time()

        if self.like_log is None:
            self.like_log = []

        self.like_log.append({
            'author': author,
            'author-url': author_url,
            'url': url,
            'timestamp': timestamp,
            'like': True
        })
        self._update_author_log(author_url=author_url, interaction_type=Interaction.LIKE)
        self.save_json_file(self.like_log_file_name, self.like_log)

    def push_comment_log(self, author, author_url, url, comment):
        """
        Push an object to be serialized with the comment log
        """
        timestamp = time.time()

        if self.comment_log is None:
            self.comment_log = []

        self.comment_log.append({
            'author': author,
            'author-url': author_url,
            'url': url,
            'comment': comment,
            'timestamp': timestamp
        })
        self._update_author_log(author_url=author_url, interaction_type=Interaction.COMMENT)
        self.save_json_file(self.comment_log_file_name, self.comment_log)

    def push_play_log(self, author, author_url, url, play_time):
        """
        Push an object to be serialized to the play log.
        """

        timestamp = time.time()

        if self.play_log is None:
            self.play_log = []

        self.play_log.append({
            'author': author,
            'author-url': author_url,
            'url': url,
            'play_time': play_time,
            'timestamp': timestamp
        })
        self.save_json_file(self.play_log_file_name, self.play_log)

    def has_commented_on_track(self, url):
        if self.comment_log is None:
            self.comment_log = []
            return False

        for log in self.comment_log:
            if log['url'] == url:
                return True

        return False

    def has_liked_track(self, url):
        if self.like_log is None:
            self.like_log = []
            return False

        for log in self.like_log:
            if log['url'] == url:
                return True

        return False

    def has_played_track(self, url):
        if self.play_log is None:
            self.play_log = []
            return False

        for log in self.play_log:
            if log['url'] == url:
                return True

        return False

    def has_posted_comment_in_past_days_on_profile(self, url, days=5):
        """
        Used to check if we can comment on any of the authors links...
        It's proven that users don't like receiving multiple messages about the same thing.
        """

        if url not in self.author_log.keys():
            return False

        url_comment_date = datetime.datetime.fromtimestamp(self.author_log[url]['timestamp'])
        now = datetime.datetime.now()

        days_difference = (now - url_comment_date).days
        # print(f"Last comment on {url} is {url_comment_date} {days_difference} days ago")

        if days_difference <= days:
            return True

        return False

    def begin(self):
        super(AudioMackBot, self).begin()

        self.driver.get("https://audiomack.com/rap/songs")

        time.sleep(random.randint(self.config['page_load_wait_time_min'], self.config['page_load_wait_time_max']))

        # Scroll page and load elements
        for i in range(1, random.randint(5, 10)):
            self.send_keypress_to_page(count=3, sleep_time=2)

        # REcently Added Author Page Links

        author_links_elements = None

        try:
            author_links_elements = WebDriverWait(self.driver, timeout=10).until(
                EC.presence_of_all_elements_located((By.XPATH, Xpaths.RECENTLY_ADDED_PAGE_ARTIST_LINKS)))
        except Exception as ex:
            pass

        author_links = []

        if author_links_elements is None or len(author_links_elements) < 1:
            self.debug(f"No author links collected")
            return

        for element in author_links_elements:
            link = element.get_attribute('href')
            if link not in author_links and not self.has_posted_comment_in_past_days_on_profile(link, 14):
                author_links.append(link)

        for author_link in author_links:

            if self.has_posted_comment_in_past_days_on_profile(author_link, days=14):
                self.debug(f"Skipping anything with {author_link} due to recent interactions with them.")
                continue

            self.driver.get(author_link)

            time.sleep(random.randint(self.config['page_load_wait_time_min'], self.config['page_load_wait_time_max']))
            self.debug(f"Finished loading author page {author_link}")

            self.send_keypress_to_page(count=4, sleep_time=2)

            music_song_link_elements = None

            try:

                author_name = self.driver.find_element_by_xpath(Xpaths.USER_PROFILE_ARTIST_NAME).text
            except:
                self.debug(f"Unable to retrieve authors name from link {author_link}")
                continue

            try:
                music_song_link_elements = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_all_elements_located((By.XPATH, Xpaths.USER_PROFILE_SONG_LINK)))
                self.debug(f"User {author_name} has {len(music_song_link_elements)} songs posted")
            except Exception as ex:
                print(ex)
                self.debug(f"Unable to collect user song links")
                continue

            music_song_links = []

            for music_element in music_song_link_elements:
                song_link = music_element.get_attribute('href')
                if song_link not in music_song_links and not self.has_commented_on_track(song_link):
                    music_song_links.append(song_link)

            if len(music_song_links) == 0:
                self.debug(f"No song links have been collected.")
                break

            # Select a random song.
            selected_song = random.choice(music_song_links)
            self.debug(f"Selected song is {selected_song}")
            # Navigate the songs.
            try:
                self.driver.get(selected_song)
            except:
                self.debug(f"Unable to navigate to {selected_song}")
                continue

            time.sleep(
                random.randint(self.config['page_load_wait_time_min'], self.config['page_load_wait_time_max']))

            # Play track and wait..

            play_button = None
            try:
                play_button = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, Xpaths.SONG_LINK_PLAY_BUTTON)))
            except Exception as ex:
                self.debug(str(ex))
                self.debug(f"Unable to locate play button on song {selected_song}")
                break

            if play_button is None:
                self.debug(f"Unable to locate play button on {selected_song}")
                break

            playing = False

            # like the track.
            if self.config['like_tracks'] is True:

                if self.has_liked_track(selected_song):
                    self.debug(f"Skipping liked track {selected_song}")
                    break

                if random.randint(1, 100) <= self.config['chance_of_like']:

                    if not playing and not self.has_played_track(selected_song):
                        # Play track logic.
                        play_button.click()
                        sleep_time = random.randint(self.config['play_time_min'], self.config['play_time_max'])
                        self.debug(f"Playing track for {sleep_time}s before next action.")
                        playing = True
                        self.push_play_log(author=author_name, author_url=author_link, url=selected_song,
                                           play_time=sleep_time)
                        time.sleep(sleep_time)

                    # like the track.
                    try:
                        like_button = WebDriverWait(self.driver, timeout=10).until(
                            method=EC.visibility_of_element_located((By.XPATH, Xpaths.USER_PROFILE_LIKE_TRACK)))
                    except:
                        self.debug(f"Unable to locate like button on song page {selected_song}")
                        continue

                    try:
                        like_button.click()
                    except:
                        continue
                    sleep_time = random.randint(self.config['like_wait_time_min'],
                                                self.config['like_wait_time_max'])
                    self.debug(f"Preparing to sleep for {sleep_time}s after liking track {selected_song}")
                    self.push_like_log(author=author_name, author_url=author_link, url=selected_song)
                    time.sleep(sleep_time)

            if self.config['commenting'] is True:

                if self.has_posted_comment_in_past_days_on_profile(author_link, days=14):
                    self.debug(
                        f"Skipping comment on {selected_song} of {author_name} as we've posted in the last 14 days.")
                    continue

                if self.has_commented_on_track(selected_song):
                    self.debug(f"Skipping duplicate comment on track {selected_song}")
                    continue

                if random.randint(1, 100) <= self.config['chance_of_comment']:
                    if not playing:
                        play_button.click()
                        sleep_time = random.randint(self.config['play_time_min'], self.config['play_time_max'])
                        self.debug(f"Playing track for {sleep_time}s before next action.")
                        playing = True
                        self.push_play_log(author=author_name, author_url=author_link, url=selected_song,
                                           play_time=sleep_time)

                        time.sleep(sleep_time)

                    try:
                        comment_box = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, Xpaths.SONG_LINK_COMMENT_BOX)))

                    except Exception as ex:
                        self.debug(str(ex))
                        self.debug(f'Unable to find comment box on {selected_song}')
                        continue

                    try:
                        self.scroll_into_view(comment_box)
                    except Exception as e:
                        self.debug(str(e))
                        self.debug(f"Unable to scroll to comment box on page {comment_box}")
                        continue

                    comment = self.generate_comment_from_spintax(author_name=author_name)

                    try:
                        self.driver.execute_script("window.scrollTo(0, 450)")
                    except:
                        self.debug(f"Error scrolling to comment button on track {selected_song}")
                        continue

                    comment_box.send_keys(comment)

                    try:
                        comment_button = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, Xpaths.SONG_LINK_POST_COMMENT_BUTTON)))
                    except Exception as ex:
                        self.debug(str(ex))
                        self.debug(f"Unable to locate comment button on track {selected_song}")
                        continue

                    # comment on song.
                    self.debug(f"Preparing to comment on {selected_song}")
                    time.sleep(random.randint(self.config['comment_write_post_wait_time_min'],
                                              self.config['comment_write_post_wait_time_max']))

                    try:
                        comment_button.submit()
                    except Exception as ex:
                        self.debug(f"First attempt to post comment on {selected_song} failed...")
                        self.debug(str(ex))
                        self.debug('... Second attempt...')
                        try:
                            comment_box.submit()
                            self.debug("... SUCCESS! COMMENT POSTED")
                        except:
                            self.debug(f'Second attempt failed... Trying click as final hope.')
                            comment_button.click()
                        continue

                    sleep_time = random.randint(self.config['comment_wait_time_min'],
                                                self.config['comment_wait_time_max'])

                    self.debug(f"Posted comment on {selected_song}.. Preparing to sleep for {sleep_time}s")
                    self.push_comment_log(author=author_name, author_url=author_link, url=selected_song,
                                          comment=comment)
                    time.sleep(sleep_time)
                    continue


if __name__ == "__main__":
    bot = AudioMackBot()
    while True:
        bot.begin()
