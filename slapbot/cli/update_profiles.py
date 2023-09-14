import math
import threading
import time
import traceback
from datetime import datetime, timedelta
from operator import or_
from typing import List

import click
import timeago
import tqdm
from selenium.common import TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from slapbot import utils, db
from slapbot.app import app
from slapbot.bots import BrowserBotBase, DriverType
from slapbot.bots.slaps import SlapBot, SlapBotXpaths
from slapbot.models import SlapsUser, SlapsComment, SlapsDirectMessage, SlapsUserUpload, Location, UserProfile, \
    SpotifyArtist, SpotifyTrack, Tag


class SlapsScraperBot(SlapBot):
    """
    Updates user information from Slaps.
    """

    def __init__(self, headless=False, driver_type=DriverType.FIREFOX, users=None):
        super().__init__(driver_type=driver_type, headless=headless)
        self.config_file_name = "slaps_user_updater_bot_config.json"
        self.late_init = True
        self.debug_silence = False
        self.users = users

        self._config = dict(
            debug=True,
            config_reload_time=20,
            tag_filter_enabled=True,
            tag_filter=[
                "HipHop",
                "Rap",
                "Trap",
                "TrapMusic",
                "MelodicRap",
                "RealHipHop",
                "UndergroundHipHop",
            ],

        )

    def startup(self):
        if not self.setup_complete:
            try:
                db.create_all()
                print("Created database tables")
            except Exception as e:
                print(e)
                return

            try:
                self.debug(f" ~ Loading config from {self.config_file_name})")
                self._config = utils.load_config(config_file_name=self.config_file_name, default_config=self._config)
            except Exception as e:
                print(e)
                return
            print(f"+ Loaded {self.config_file_name}")

            if self.late_init is True:
                print(
                    f"Initializing browser")
                self.init_driver(use_profile=False)

            self.setup_complete = True

    def begin(self, offset=0, limit=1000, days=2, all_users=False):
        """Launch the scraper. Will update information of all the users handed to it."""
        if not self.setup_complete or self.driver is None:
            self.startup()

        if not all_users:
            last_day = datetime.utcnow() - timedelta(days=days)

            if self.users is None:

                users = SlapsUser.query.filter(
                    or_(SlapsUser.updated_at <= last_day, SlapsUser.profile_url == None)).order_by(
                    SlapsUser.updated_at.asc()).offset(offset).limit(limit).all()
            else:
                users = self.users
        else:
            users = SlapsUser.query.offset(offset).limit(limit).all()

        user_count = len(users)

        for user in users:
            if isinstance(user, str):
                user = SlapsUser.query.filter_by(username=user).first()

            if user is None:
                continue

            if user.profile_url is None:
                user.profile_url = f"http://slaps.com/{user.username}"

            if not self.scrape_user_data(user):
                self.debug(f"Failed to scrape user data", fg="red")

            user.save(commit=True)

    def scrape_user_data(self, user: SlapsUser, progress_bar: tqdm = None) -> bool:
        """
        Scrape the user information by going to their page.
        """

        profile = UserProfile.query.filter_by(slaps_user_id=user.id).first()

        if profile is None:
            profile = UserProfile(slaps_user_id=user.id)
            profile.save(commit=False)

        # verification request
        if self.driver.current_url is not user.profile_url:
            try:
                self.driver.get(user.profile_url)
            except:
                traceback.print_exc()
                self.debug(f"~ Failed to load {user.profile_url}", fg="red")
                return False
            # self.scroll_down_with_key_press()

        if self.handle_cookie_consent():
            self.debug("Cookie consent detected & closed")

        if self.handle_creditcard_renewal_menu():
            self.debug("Credit card renewal menu detected & closed")

        if self.check_for_user_not_found_element():
            user.delete(commit=False)
            self.debug(f"~ User {user.username} was not found, deleting from database", fg="red")
            return False

        if self.has_error_page():
            click.secho(f"~ Error page detected, skipping {user.username}", fg="red")
            return False

        if self.handle_alert_dialog():
            self.debug(f"~ Alert dialog detected, closing", fg="red")
            return False

        try:
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, SlapBotXpaths.USER_PAGE_USERNAME_ELEMENT.value))
            )
        except:
            user.delete(commit=False)
            self.debug(f"~ Failed to find username element on {user.profile_url}", fg="red")
            return False

        username = username.text.strip()
        user.username = username
        self.debug(f" ~ Updated username for {user.username} to {username}", fg="cyan", underline=True)

        try:
            social_media_links = WebDriverWait(self.driver, timeout=3).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_SOCIAL_MEDIA_LINKS.value)
                )
            )
            for link in social_media_links:
                self.scroll_into_view(link)
                self.update_social_media_url(user, link)
            self.update_profile_socials(user)
        except Exception as e:
            pass

        try:
            bio = WebDriverWait(self.driver, timeout=1).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_BIO_TEXT.value)
                )
            )
            self.scroll_into_view(bio)
            user.description = bio.text.strip()
        except:
            pass

        try:
            followers_count = WebDriverWait(self.driver, timeout=3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_FOLLOWERS_COUNT.value)
                )
            )
            user.follower_count = int(followers_count.get_attribute('innerHTML').replace(",", ""))
            self.debug(f" ~ Followers on {user.username} count: {user.follower_count}", fg="green")
        except:
            pass

        if not self.has_to_login:
            follow_button: WebElement = None
            try:
                follow_button = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located(
                        (By.XPATH,
                         SlapBotXpaths.USER_PAGE_FOLLOW_BUTTON.value)
                    )
                )
                self.scroll_into_view(follow_button)
            except:
                self.debug(f"~ Failed to find follow button on {user.profile_url}", fg="red")
                return False

            button_text = follow_button.text

            already_following = False

            if button_text == "Following":
                if user.following_on_slaps is False:
                    self.debug(f"Updated user who we were following: {user.username}")
                    user.following_on_slaps = True

            elif button_text == "Follow":
                follow_button.click()
                user.following_on_slaps = True
                self.debug(f" + Followed user: {user.username}", fg="green")

            """
            Update the users slaps messaging link so we can skip navigating to profile if we don't have to
            """
            try:
                # After following, we can send them a message!
                message_button = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                         '//div[@class="slapInfoBoxInside"]//a[contains(@onclick,"return allowSlapsDirectMessage();")]')
                    )
                )
                self.scroll_into_view(message_button)
                # message_button.click()

                message_url = message_button.get_attribute('href')
                if user.message_url is None or user.message_url is not message_url:
                    user.message_url = message_url

            except Exception as e:
                user.save(commit=False)
                self.debug(f"~ Failed to find message button on {user.profile_url}", fg="red")
                return False

        try:
            joined_date = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_JOIN_DATE_TEXT.value)
                )
            )
            user.joined_date = joined_date.text.strip()
        except:
            pass

        try:
            play_count_total = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_PLAY_COUNT.value)
                )
            )
            user.play_count = int(play_count_total.text.strip().replace(",", ""))
        except:
            pass

        try:
            user_location = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_LOCATION_TEXT.value)
                )
            )

            location = Location.query.filter_by(name=user_location.text.strip()).first()
            if location is None:
                location = Location(name=user_location.text.strip())
                location.save(commit=False)

            user.location_id = location.id
            user.save(commit=False)
        except:
            pass

        try:
            user_page_avatar = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_AVATAR_IMAGE.value)
                )
            )
            self.scroll_into_view(user_page_avatar)
            user.profile_image_url = user_page_avatar.get_attribute('src')
        except:
            pass

        track_count = 0
        try:
            track_count = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_TRACK_COUNT.value)
                )
            )

            track_count = int(track_count.text.strip().replace(",", ""))
        except:
            pass

            self.debug(f"~ {user.username} has {track_count} tracks uploaded", fg="yellow")

        self.debug(f" ~ Checking if {user.username} has posted recently", fg="cyan")
        try:
            recently_active_header = self.driver.find_element(By.XPATH,
                                                              SlapBotXpaths.USER_PAGE_TOP_POST_HEADER.value)
            recent_text = recently_active_header.text.strip().lower()
            if 'min ago' in recent_text or 'hours ago' in recent_text or 'days ago' in recent_text or 'yesterday' in recent_text:
                user.recently_posted = True
                user.save()

        except:
            pass

        successive_failures = 0

        while True:
            if successive_failures >= track_count:
                break
            try:
                end_of_posts = WebDriverWait(self.driver, 1).until(
                    EC.presence_of_element_located('//div[@style="height:100px;text-align:center;"]')
                )
                break
            except:
                self.scroll_with_javascript(700)
                successive_failures += 1
                pass

        self.debug(f" ~ Processing {user.username}'s tracks", fg="green")
        try:
            player_boxes = WebDriverWait(self.driver, 1).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, '//div[@id="putSongsHere"]//div[contains(@class,"playerBox")]'))
            )
        except:
            self.debug(f"~ Failed to find any tracks for {user.username}", fg="yellow")
            return False

        self.debug(f" ~ Found {len(player_boxes)} tracks by {user.username}", fg="cyan")

        for player_box in player_boxes:
            self.scroll_into_view(player_box)
            try:
                track_share_button = player_box.find_element(By.XPATH, './/div[contains(@onclick,"Share")]')
                self.scroll_into_view(track_share_button)

                track_share_button.click()
                time.sleep(0.1)
            except:
                pass

            try:
                close_track_share_dialog = WebDriverWait(self.driver, 1).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//body[@class="modal-open"]//i[contains(@onclick,"slapsClose")]'))
                )
                close_track_share_dialog.click()
            except:
                pass

            try:
                track_url = WebDriverWait(self.driver, timeout=1).until(
                    EC.presence_of_element_located((By.XPATH, '//input[contains(@class,"shareUrl")]'))
                )

                track_url = track_url.get_attribute('value')
                media_url = player_box.find_element(By.XPATH, './/div[@class="slapWaveform"]/audio').get_attribute(
                    'src')
                track_title = player_box.find_element(By.XPATH, './/div[contains(@title,"title")]').text.strip()
                artwork_url = player_box.find_element(By.XPATH, './/img[@class="slapWaveArtwork"]').get_attribute('src')

                # Expand the tracks description
                track_description = None
                try:
                    track_description = player_box.find_element(By.XPATH,
                                                                './/div[@class="slapSongNotes"]').text.strip()
                    self.scroll_into_view(track_description)
                    track_description.click()
                except:
                    pass

                tags = []

                try:
                    track_tags_elements = player_box.find_elements(By.XPATH,
                                                                   './/div[@class="slapGroupsContainer"]//a')

                    for tag_href in track_tags_elements:
                        tag_name = tag_href.get_attribute('href').split("group/")[1]

                        if self.config['tag_filter_enabled'] is True and tag_name not in self.config['tag_filter']:
                            continue

                        tag = Tag.get_or_create(tag=tag_name)
                        tags.append(tag)
                        self.debug(f" ~ Found tag {tag_name} on {track_title} by {user.username}", fg="cyan")
                except Exception as e:
                    traceback.print_exc()
                    self.debug(f" ~ Failed to find any tags on {track_title} by {user.username}", fg="yellow")
            except:
                continue

            try:
                spotify_url = player_box.find_element(By.XPATH, './/a[@title="spotify"]').get_attribute('href')

                if "artist" in spotify_url:
                    spotify_artist = SpotifyArtist.query.filter_by(url=spotify_url).first()

                    if spotify_artist is None:
                        spotify_artist = SpotifyArtist(url=spotify_url)
                        spotify_artist.save(commit=False)

                    profile.spotify = spotify_artist
                    profile.save(commit=False)

                elif "track" in spotify_url:
                    spotify_track = SpotifyTrack.query.filter_by(url=spotify_url).first()

                    if spotify_track is None:
                        spotify_track = SpotifyTrack(url=spotify_url)
                        spotify_track.save(commit=False)

                    if profile is not None and profile.spotify:
                        spotify_track.artist = profile.spotify
                        spotify_track.save(commit=False)
            except:
                pass

            self.debug(f" ~ Processing track {track_title} by {user.username} @ {track_url}", fg="yellow")
            upload = SlapsUserUpload.query.filter_by(track_url=track_url).first()

            if upload is None:
                upload = SlapsUserUpload(track_url=track_url, user_id=user.id, track_title=track_title,
                                         description=track_description, tags=tags,
                                         artwork_url=artwork_url, media_url=media_url)
                upload.save(commit=False)
            else:
                upload.media_url = media_url
                upload.track_title = track_title
                upload.artwork_url = artwork_url
                upload.save(commit=False)

        return True


def update_slaps_data(threads: int = 1, headless: bool = True,
                      driver_type: DriverType = DriverType.FIREFOX, days: int = 1, users: List[str] = None,
                      all_users=False, **kwargs):
    """Fixes profiles / users that are missing any sort of data."""
    click.secho(f"~ Retrieving data from database.", fg="green")

    last_day = datetime.now().utcnow() - timedelta(days=days)

    if not all_users:
        users_count = SlapsUser.query.filter(
            or_(SlapsUser.updated_at <= last_day, SlapsUser.profile_url == None)).count() if users is None else len(
            users)
    else:
        users_count = SlapsUser.query.count()
    click.secho(f"~ Starting multi-threaded process with {threads} threads & {users_count} users.", fg="green",
                bold=True)
    max_users_per_thread = users_count / threads
    if users_count == 0 or max_users_per_thread == 0:
        click.secho(f" ~ There are no users requiring fixing. Exiting.")
        return
    click.secho(f"~ Max users per thread: {max_users_per_thread}", fg="green", bold=True)
    pages = users_count / max_users_per_thread

    def scraper_task(offset, limit, users=None):
        with app.app_context():
            slaps_scraper_bot = SlapsScraperBot(headless=headless, driver_type=driver_type, users=users)
            slaps_scraper_bot.begin(offset=offset, limit=limit, days=days, all_users=all_users)

    active_threads = []

    for page_num in range(0, int(pages)):
        click.secho(f"~ Creating thread for page {page_num}", fg="green", bold=True)
        offset = page_num * max_users_per_thread

        thread = threading.Thread(target=scraper_task, args=(offset, max_users_per_thread, users))
        active_threads.append(thread)
        thread.start()

        if len(active_threads) >= threads:
            click.secho(f"~ Waiting for threads to finish before creating new instances.", fg="green", bold=True)
            for thread in active_threads:
                thread.join()

            active_threads = []

        page_num += 1

    click.secho(f"~ Finished multi-threaded profile update.", fg="cyan", bold=True)

    return


def _fix_youtube_data():
    pass
