import datetime
import enum
import json
import os
import pprint
import random
import time
import traceback
from typing import List, Tuple

import click
import jellyfish
import requests
from bs4 import BeautifulSoup
from selenium.common import TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import or_
from tqdm import tqdm

from slapbot.ai.chatgpt import ChatGPT3APIWrapper
from slapbot.bots import BrowserBotBase, DriverType
from slapbot import utils

from slapbot import db
from slapbot.models import SlapsUser, ScraperLog, SlapsDirectMessage, ActionLog, SlapsComment, SlapsUserUpload, \
    UserProfile, YoutubeChannel, TwitterProfile, FacebookUser, InstagramProfile, Location, SpotifyTrack, SpotifyArtist, \
    Tag


class SlapBotXpaths(enum.Enum):
    USER_PAGE_FOLLOW_BUTTON = '//div[@class="slapInfoBoxInside"]//span[contains(@class,"mainUserFollowButton")]'
    USER_PAGE_USER_NOT_FOUND = '//div[@class="playerBox" and contains(@style,"text-align: center;font-weight: 400;")]'
    USER_FOLLOWERS_PAGE_USER_USERNAME_ELEMENT = '//div[@style="min-height: inherit;padding: 15px;"]//div[1]'
    USER_FOLLOWERS_PAGE_NOBODY_FOUND_ELEMENT = "//div[@class='slapPageContainer slapPageContainerStandalone slapsBoxShadow']//div//div[@style='font-weight: 400;padding:15px;text-align: center;padding-top: 100px;']"
    USER_FOLLOWING_PAGE_NOBODY_FOUND_ELEMENT = USER_FOLLOWERS_PAGE_NOBODY_FOUND_ELEMENT
    USER_FOLLOWERS_PAGE_FOLLOWER_LINK_ELEMENT = "//div[contains(@class,'peopleRow pointer')]//a"
    USER_FOLLOWERS_PAGE_FOLLOWER_USERNAME_ELEMENT = "//span[@class=\"slapsPeopleList\"]//div[2]//span[@class=\"bold\"]"
    USER_FOLLOWERS_PAGE_FOLLOWER_DESCRIPTION_ELEMENT = "//span[@class='slapsPeopleList']//div[2]//div[3]"
    USER_PAGE_USERNAME_ELEMENT = '//div[@class="slapsDisplayName"]//span[@class="bold"]'
    USER_PAGE_SOCIAL_MEDIA_LINKS = "//a[@target='_blank']//div[@class='slapInfo']"
    USER_PAGE_TOP_POST_HEADER = '//span[@class="mobileHideInline"]'
    USER_PAGE_FOLLOWERS_COUNT = '//a[contains(@href,"followers")]//div[contains(@style,"font-size")]/b'
    USER_PAGE_AVATAR_IMAGE = '//img[@class="slapAvatarImg"]'
    USER_PAGE_PLAY_COUNT = '//div[@class="slapsDisplayName"]/div[1]/div[3]/div[3]/b'
    USER_PAGE_TRACK_COUNT = '//div[@class="slapsDisplayName"]/div[1]/div[3]/div[1]/b'
    USER_PAGE_BIO_TEXT = '//div[@class="slapInfoBoxInside"]//div[@class="bioText"]'
    USER_PAGE_LOCATION_TEXT = '//div[@style="font-size: 13px;letter-spacing: 0.25px;margin-top: 2px;"]'
    USER_PAGE_JOIN_DATE_TEXT = '//div[text()[contains(.,"Joined")]]'
    ERROR_PAGE_XPATH = "//font[@face='arial' and @size=\"4\"]"
    USER_PAGE_MESSAGE_BUTTON = '//div[@class="slapInfoBoxInside"]//a[contains(@onclick,"return allowSlapsDirectMessage();")]'
    ALERT_DIALOG_BUTTON_CLOSE_XPATH = "//div[@class=\"swal2-actions\"]//button[text()[contains(.,'OK')]]"
    INBOX_PAGE_LOADING_ELEMENT = '//div[@id="messageHere"]//i[@class="fa fa-circle-o-notch fa-spin fa-fw"]'
    INBOX_PAGE_MESSAGE_TEXTAREA = '//div[@id="js-message-inner-container"]'
    INBOX_PAGE_ALL_MESSAGES_SENT = '//div[@class="message_me inboxMessage"]//div[@class="message-text"]'
    INBOX_PAGE_MESSAGE_RECEIVED_NON_BULK = '//div[@class="message_you inboxMessage"]'
    INBOX_PAGE_MESSAGE_RECEIVED_BULK = '//div[@class="message_you_bulk inboxMessage"]'
    INBOX_PAGE_MESSAGE_RECEIVED_MESSAGE_TEXT = './/div[@class="message-text"]'


class SlapBot(BrowserBotBase):
    """
    Private messaging bot for Slaps.com.

    Will send a message to a user if they have not been messaged before (with that message)
    after following them to do so.

    Scrapes users from the frontpage.
    """

    def __init__(self, headless: bool = False, driver_type=None, config=None, testing=False):
        super().__init__(driver_type=driver_type, late_init=True,
                         headless=headless)

        self._chat_gpt_api: ChatGPT3APIWrapper = None
        self.sleeping_after_song_comment = False
        self.sleeping_after_messaging_scraped_lead = False
        self.sleeping_after_homepage_scrape = False
        self.sleeping_after_leads = False
        self.sleeping_after_messaging = False
        self.total_messaged_users_count = 0
        self.error_page = False
        self.config_file_name = "slapbot_config.json"
        self._config = dict(
            debug=True,
            username="Islati",
            slaps_search_url="https://slaps.com/?action=&id=&sort=",
            firefox_profile_path=self.locate_firefox_profile(),
            chrome_profile_path=self.locate_chrome_profile(),
            wait_time_min=45,
            wait_time_max=90,
            scroll_min=10,
            scroll_max=100,
            captcha_wait_time=30,
            requires_login=True,
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
            user_scraping=dict(
                followers_and_following=False,
                hot_tab=False,
                new_tab=True,
                enabled=True,
                hours_to_wait=2,
                deep_scrape_days=7,
                messaging_enabled=True,
                messaging_sleep_min=60,
                messaging_sleep_max=300,
                sleep_min=60,
                sleep_max=300,
            ),
            exits=dict(
                post_inboxing=False,
                post_unfollowed_leads_messages=False
            ),
            messaging=dict(
                check_recently_active=True,
                update_message_history=True,
                check_for_duplicates=True,
                only_message_if_not_following=True,
                similarity_limit=0.75,
                valid_inbox_thread_kill_switch_count=50,
                inbox_existing_conversations=False,
                inboxing_reverse_order=False,
                unfollowed_leads_batches=1,
                unfollowed_leads_batch_limit=500,
                ignore_duplicate_links=False,
                wait_times=dict(
                    wait_skip=True,
                    days_to_wait=10,
                    hours_to_wait=14,
                ),
            ),
            message_leads=dict(
                enabled=True,
                unfollowed=True,
                followed=True,
                sleep_min=90,
                sleep_max=3600,
            ),
            error_failsafe=dict(
                sleep_min=1600,
                sleep_max=3600
            ),
            comment_settings=dict(
                use_chat_gpt=False,
                use_openai=False,
                open_ai_secret_key="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",
                chat_gpt_session_token="eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..GgfFvnhSyJvgrJL6.GD4FqciUA1h941WfLwZJAXRt_Ye6g5kisrthVzDcPRzpGMrr_HvWrkrPzfEsHW8eQ_IrH02WeTwOsXVlntfqC9KdNA3N2e-Uhsf2iPgaDp_XeP6hT3Al8hatt1HWZsPe3GPmsbmpxjQfyfVNKylF89nmux4qWAnS2KOqdfFpUzB-6XFDv6VCaHVdum3yHg3MI4Rhm0E4ffY-lsDQbRImO01qSLMplhe3HxX_x2bKd9LXbaTDTX9Mn9hijmYVt_nRlObX6Kpns--rlqa_VcwLsuR5NTTAfKX5PVJ60-ub-iS04RtuUmYe34dH3aPxpEJ4acwdK6xEHpHgP7yDRa6Ag3Cgl9mlUIc8iGPSIqaQS5yIsMLeZon7WKlLu_KAwXKLsy-Y0jgxbXlbIHzL3hGVPjgRTVMtvaG6bodWrWh7zQPe709HcbFaxpimqve66Zfx7cciJIJQ4UgybgKSA08oCCvZWvO58L60Mn4Nn2ejPOQ6zsdI8Buo5DMFB9JZeCAGCUYb6st8aqzQCB7STeKW-ukiVh9ckJkbqrU3AAP42sLs6mOoJsIEES-soBoijaBMCYMoWZLefKRHph2ditBpKw9LIvRdXLno6FhR95kO_w5I-DuKURAg168jkBlCdr1zGtSFhHk93-G4HFjU66AwMh-3JgRA2N-OOsxb2WUB_TGTXnWfeya7Et2mu_VekRX8SPr97HfLTYVM1xswV-MHDaIvxiEgzlU1xtTLITC_kqjQDqgLSEmWwLmUvDICQM98A9Inif81KV4Zpd0CpqkrxBZq9tJ8UPj_wKX_zxjkj_5QStUtByfCWf8uyd2rROrrx-zYzrPVKO4v_DqEXU3do7IR-CBkDuA6CS0m2Lbcxa_PmPXikm-GWRb-XOUXdBe7ebOLI-pXKLd5YzkKjnCAps-5SD8bbJ6CzB324_ktC19w7kAv8Iyjshfhls_UX0oBtvq1zRrSJM0rRL3gSIkQvRiZ3juavRpv8TcPsrWk2WZUPa14TEauxqB-0rFiDZgGkp1O63XsFr5UkEdMFsUUyducVwdMtsxi0DUaS8AF9LwxKafGzqWlsabboZKlGv0A7n8rZd_Zb55JnGVXfdx2OkiZ0JPOVIK12SnUKfaH_92H77gMF3KVuV7C0syk7UG2PTvA_eB8JT1OR0djrjg3Lb40C-9-MqC1EQWD8ZcoQ25WYDRfRJ9SmZi6IwJLfe7nV9YR470wtqRhNoYJzkJLMkOfan0rvNg3QClGQf4xKhkn3Jl-4BXaEhmjg1c62V8I4uheLtuUSaP6JvoeK_Pc2dCuqNy0AAQQP3J9n14vXsFbM0CpaXOA2lhlXPXFUbkS0HBfcoaT5U6cySBVaFThlt-xNlYYD6RbZq64KC7mH4CWS-xuv39b3RgnARksWTCeB9cZHYgGPMPywY1dgHmYAOaqJCnWnLdTjMkOk252uZJmu1Up3njKkr5Co83EU8G0SZaxRJtrALwMIM0m4L0OFnnh0gEAB0yYtwUcanyRjAC2C4gxfLQrmCMJaRAA02U0ms8JUQoTHJdjS4faYOR8ROjMJG8ZYUizpEEntmGHkSpP_BrHP6UT3RFSkM4wWW8H7ijfcmEuf3ThcF_8HNzH0nGfV40slHRtFHuJcZwh3go_QgfxfwpomKaxNhjiDrOz5CIOiWtDQ7x41gMVMEhUqOf7MidlXXzl1u8Sz4NLoVqnn8seWW21EzgWXtdD30KrbBZjEaa6t8WMcYIbvgsQdIVahom-yGZBKKmq4I3vRy8Y6Dwn-ErS0forjn4HARydQ1QKEQJ5z1uIOLe0GXjejqYzMr1Eg2oXS59fA9SUL2r5s_ISJMOCJQn7X32ppmvmnrPg7AX2M6PAPMtHXWBxSOLL8s_wir_uss_rkuF9C4R6iM0jRnr_2dc48FM9aKrnUoH74JW71SdPGEXdsv5yQpxbVepjFt-23xyJ08hWRaSIr7AIdgWGi6LitI9eF95gDvMQ3OOHXsCSCPA3plO03Q0Mzrw-CyxCxJ6ISWYcpmg681IMvChqLpcFosKajK10LN8L67_GVThKfZsg18zHsPg7iqNp56A2iEFZL_nUBB_7WzGXVIGucYCltlG4Dn1Z61NEGg38u0CCh89uFlIlE6Vc1vKIsmFp6ryuI07Cjk3oqHTbMj9fVnSoh4BxffiWE744-vmDoWhYtkz4o8h9fFCwaXRWmXCS_1yrvX_rp2KYDrxs5XdPB_eNT6xhSH7txPrXP3k2t8NymAgbqHE.CWCRvAbSgzVgR63Sh3oiMQ"
            ),
            direct_messages=[
                "Hey, what's up [author] Check out [songplug]"
            ],
            comments=[

            ],
            descriptive_tags={
                "songplug": [
                    "my new music video `Still Dreaming` on YouTube at https://youtu.be/9Ho4SyBYtSU & ask them to like, comment and subscribe.",
                    "my new rap song `Free Game` available at http://free-game.skreet.ca to listen on all platforms & ask them put it on a playlist and to keep in touch",
                ]
            },
            ai_prompts={
                "direct_message": [
                    "Can you write a direct message to [author]? Tell them about my new music video [songplug]. Be sure to include {lots of|} emojis to make it more personal, and thank them for their support.",
                ],
                "direct_messaging_reply": [
                    "Can you reply to [author] with a direct message? They wrote `[reply]`. Tell them about my new music video [songplug] & include emojis to personalize it"
                ],
                "song_comment": [
                    "Can you write a new comment for [author] on their song [song] (but dont include the title)? Tell them about [songplug] Compliment them on their hard work. Include fun emojis {throughout|}"
                ]
            },

            song_liking=dict(
                enabled=True,
                like_chance=100,
                love_chance=5,
                sleep_min=5,
                sleep_max=30,
            ),
            song_commenting=dict(
                enabled=True,
                comment_chance=100,
                sleep_min=5,
                sleep_max=80,
                sort_by="new",
                scroll_min=1,
                scroll_max=15,
                max_comment_search_iterations=10,
                sleep_after_comment=True
            ),
            smart_loop=dict(
                enabled=True,
                page_refresh_time=60 * 30
            ),
            headless=headless if headless is not None else False,
            finish_restart_wait_time_min=4500,
            finish_restart_wait_time_max=6000,
            config_reload_time=20,
        ) if config is None else config
        self.headless = headless if headless is not None else False

        self.config_update_timestamp = 0

        self.timestamp_page_last_refreshed = 0
        self.sleep_page_refresh = False

        self.sleep_messaging_users = False
        self.timestamp_messaging_users = 0

        self.sleep_commenting_songs = False
        self.timestamp_commenting_users = 0

        self.sleep_slapping_songs = False
        self.timestamp_slapping_users = 0

        self.log = [

        ]

        utils.debugger.debug_silence = False
        self.println = True
        self.progress_bar = tqdm()

        self.inboxing_user_ids_cache = []

        self.sleeping_after_scraping_homepage_for_recent_users = False
        self.collected_recent_user_ids = []

        self.testing = testing

    @property
    def has_to_login(self):
        return self.is_logged_in() is False

    @property
    def chat_gpt_api(self) -> ChatGPT3APIWrapper:
        if self._chat_gpt_api is None:
            self._chat_gpt_api = ChatGPT3APIWrapper()
        return self._chat_gpt_api

    @property
    def config(self):
        if self.testing is True:
            return self._config
        timestamp = datetime.datetime.utcnow().timestamp()

        if not os.path.exists(self.config_file_name):
            utils.save_json_file(self.config_file_name, self._config)
            self.debug("Created default configuration file: slapbot_config.json")

        if self.config_update_timestamp is None or timestamp - self.config_update_timestamp >= self._config[
            'config_reload_time']:
            try:
                self._config = utils.load_config(config_file_name=self.config_file_name, default_config=self._config)
                utils.debugger.debug_silence = self._config['debug'] is False
            except Exception as e:
                traceback.print_exc()
                return self._config

            self.config_update_timestamp = timestamp
        return self._config

    @config.setter
    def config_setter(self, value):
        self._config = value

    def check_for_user_not_found_element(self):
        try:
            user_not_found_element = WebDriverWait(self.driver, timeout=10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_USER_NOT_FOUND)
                )
            )
            return "not found" in self.driver.page_source
        except:
            return False

    def scrape_users_from_users_pages(self, user, cli_bar=None, retrying=False):
        """
        Iterate through users that have been collected, see their followers,
        see who's following, and create profiles for these users aswell.

        e.g. https://slaps.com/islati/following & https://slaps.com/islati/followers
        """

        cli_bar = self.progress_bar if self.progress_bar is not None else cli_bar
        if cli_bar is None:
            cli_bar = tqdm()

        self.debug(f"Navigating to followers page @ {user.followers_url}")
        self.driver.get(user.followers_url)

        if self.handle_creditcard_renewal_menu():
            self.debug("Credit card renewal menu detected, closing", progress_bar=cli_bar)

        if self.has_error_page():
            self.debug(f"Error page when navigating to {user.username} followers page", progress_bar=cli_bar)

            if retrying is False:
                sleep_time = self.get_random_messaging_sleep_time() / 2
                self.debug(f"Error when navigating to {user.username} followers - Retrying in {sleep_time}s",
                           progress_bar=cli_bar)
                time.sleep(sleep_time)
                return self.scrape_users_from_users_pages(user=user, cli_bar=cli_bar, retrying=True)

            return []

        if self.check_for_user_not_found_element():
            user.delete(commit=True)
            self.debug(f'Deleted {user.username} as they no longer exist', progress_bar=cli_bar)
            return []

        try:
            username_element = WebDriverWait(self.driver, timeout=10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_FOLLOWERS_PAGE_USER_USERNAME_ELEMENT.value)
                )
            )

            found_username = username_element.text.strip()

            if user.username is not found_username and 'not available' not in found_username and "doesn't exist" not in found_username:
                user.username = found_username
                self.debug(f"Username is {user.username}")
                user.save(commit=True)
                self.debug(f"Updated username to {user.username}")
        except:
            self.debug("Unable to update username of " + user.username)
            pass

        def parse_page_source_for_users() -> List[SlapsUser]:
            try:
                nobody_found = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                         SlapBotXpaths.USER_FOLLOWERS_PAGE_NOBODY_FOUND_ELEMENT.value)
                    )
                )
                self.debug("Nobody found!")
                return []
            except:
                pass

            user_ids = []
            processed_urls = set()
            all_done = False
            while not all_done:
                try:
                    followers_links = WebDriverWait(self.driver, timeout=10).until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, SlapBotXpaths.USER_FOLLOWERS_PAGE_FOLLOWER_LINK_ELEMENT.value)
                        )
                    )

                    for follower_link in followers_links:
                        # self.scroll_into_view(follower_link)

                        url = follower_link.get_attribute('href')
                        if url in processed_urls:
                            continue

                        username = follower_link.find_element(By.XPATH,
                                                              SlapBotXpaths.USER_FOLLOWERS_PAGE_USER_USERNAME_ELEMENT.value).text.strip()

                        if not SlapsUser.query.filter_by(profile_url=url).first():
                            found_user = SlapsUser.find_or_create(url, username)
                            user_ids.append(found_user)
                            processed_urls.add(url)
                        else:
                            found_user = SlapsUser.find_or_create(url, username)

                        try:
                            description = follower_link.find_element(By.XPATH,
                                                                     SlapBotXpaths.USER_FOLLOWERS_PAGE_FOLLOWER_DESCRIPTION_ELEMENT.value)
                            _description = description.text
                            found_user.description = _description.strip()
                            found_user.save(commit=True)
                        except:
                            pass

                    return user_ids
                except:
                    continue

        user_ids = parse_page_source_for_users()
        cli_msg = f"Collected {len(user_ids)} new users from {user.username} followers @ {user.followers_url}"
        # self.debug(cli_msg)
        self.debug(cli_msg, progress_bar=cli_bar)
        ScraperLog.get_or_create(url=user.profile_url, collected_user_count=len(user_ids), user_ids=user_ids)

        # self.debug(f"Navigating to {user.following_url} for {user.username}")
        try:
            self.driver.get(user.following_url)

            if self.handle_creditcard_renewal_menu():
                self.debug("Credit card renewal menu detected, closing")

        except:
            self.debug(f"Timeout when navigating to {user.following_url}")
            return []  # Happens when timeout occurs.
        if self.has_error_page():
            self.debug(f"Error page when navigating to {user.username} following page")

            if retrying is False:
                sleep_time = self.get_random_messaging_sleep_time() / 2
                self.debug(
                    f"Error when navigating to {user.username} following - Retrying in {sleep_time}s")
                time.sleep(sleep_time)
                return self.scrape_users_from_users_pages(user=user, cli_bar=cli_bar, retrying=True)

            return []

        user_ids = parse_page_source_for_users()
        cli_msg = f"Collected {len(user_ids)} new users from {user.username} following list @ {user.following_url}"
        # self.debug(cli_msg)
        self.debug(cli_msg, progress_bar=cli_bar)
        ScraperLog.get_or_create(url=user.profile_url, collected_user_count=len(user_ids), user_ids=user_ids)

        user.deep_scraped = True
        user.deep_scrape_completion_timestamp = datetime.datetime.now()
        user.save(commit=True)

        self.debug(f"Deep scraping of {user.username} is complete", progress_bar=cli_bar)

    def scrape_users_from_slaps_homepage(self, sort="new") -> List[SlapsUser]:
        """
        Collect user information from the slaps homepage.
        These should be added to the database, and also returned to be processed
        in this session (or another, granted the session fails)
        """
        collected_users = []

        try:
            self.driver.get(self.config["slaps_search_url"] + sort)
        except:
            return []

        if self.handle_creditcard_renewal_menu():
            self.debug("Credit card renewal menu detected, closing")

        scroll_selection = range(random.randint(self.config['scroll_min'], self.config['scroll_max']))
        for i in tqdm(scroll_selection):
            self.scroll_with_javascript(random.randint(1000, 1400))
            time.sleep(0.5)

        try:
            author_url_elements = self.driver.find_elements(By.XPATH, '//span[@class="slapDisplayName"]/parent::a')
        except Exception as ex:
            print(traceback.format_exc())
            exit(9)
            return []

        # author_url_elements = author_url_elements[2:]  # Skips "Hot & New"

        author_url_elements = tqdm(author_url_elements)
        for element in author_url_elements:
            author_href = element.get_attribute('href')
            author_name = element.find_element(By.CLASS_NAME, 'slapDisplayName').text.strip()

            author_url_elements.set_description(f"{author_name} at {author_href}")
            user = SlapsUser.find_or_create(author_href, author_name)
            if user is None:
                author_url_elements.set_description(
                    f"When creating User() object with {author_href} for {author_name} there was a bug")
                continue

            collected_users.append(user)

        '''
        Iterate through collapsed comment sections on the website and collect user information.
        '''
        expand_comments_elements = []

        try:
            expand_comments_elements = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH,
                     '//div[@class="slapTotalCommentsContainer" and not(contains(@style,"display: none"))]//div[@class="showMoreTop"]//div[@class="linklike"]')
                )
            )
        except TimeoutException as ex:
            pass

        if expand_comments_elements is not None and len(expand_comments_elements) > 0:
            i = 0
            for element in expand_comments_elements:
                try:
                    self.scroll_into_view(element)
                    element.click()
                except:
                    continue
                self.debug(f"Expanding comment section ({i}/{len(expand_comments_elements)})")
                i += 1
                time.sleep(0.2)

                breakout_broken = False
                more_loaded = False

                tries = 0
                max_tries = 10
                while breakout_broken is False and more_loaded is False:
                    if tries >= max_tries:
                        break
                    show_more_comments = None
                    try:
                        show_more_comments = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_all_elements_located(
                                (By.XPATH,
                                 "//div[@class='showMoreBottom'][contains(@style,'display: block')]//div[@class='linklike']")
                            )
                        )
                    except:
                        breakout_broken = True
                        break

                    if show_more_comments is None:
                        self.debug('No \'Show More Comments\' button')
                        break

                    self.debug(
                        f"Iterating 'Show more Comments' buttons to expand ({len(show_more_comments)} total)")
                    for show_more_button in show_more_comments:
                        try:
                            self.scroll_into_view(show_more_button)
                        except:
                            breakout_broken = True
                            break
                        try:
                            show_more_button.click()
                            self.debug('More comments loaded')
                            more_loaded = True
                        except:
                            breakout_broken = True
                            self.debug("Unable to expand comment section- breaking out of loop")
                            break
                        time.sleep(0.2)

                    tries += 1

        try:
            commentor_url_elements = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, '//div[@class="slapCommentMetadata"]//a[@class="slapCommentUserLink"]')
                )
            )
        except:
            return collected_users

        for comment in commentor_url_elements:
            profile_url = comment.get_attribute('href')
            username = comment.find_element(By.XPATH, './/span[@class="slapCommentName"]').text.strip()
            user = SlapsUser.find_or_create(profile_url, username)
            # Avoid collecting users who we've recently messaged.
            if not self.config['messaging']['wait_times']["wait_skip"] and SlapsUser.has_sent_message(user=user, days=
            self.config['messaging']['wait_times']["days_to_wait"],
                                                                                                      hours=self.config[
                                                                                                          'messaging'][
                                                                                                          'wait_times'][
                                                                                                          "hours_to_wait"]):
                continue
            collected_users.append(user)

        return collected_users

    def get_random_messaging_sleep_time(self):
        return random.randint(self.config['wait_time_min'], self.config['wait_time_max'])

    def update_profile_socials(self, user):
        """
        Updates the user's profile with their social media information.
        :param user: The user to update.
        """

        user_profile = UserProfile.query.filter_by(slaps_user_id=user.id).first()
        if user_profile is None:

            user_profile = UserProfile(slaps_user_id=user.id)
            user.profile_id = user_profile.id
            user.profile = user_profile
        else:
            user.profile_id = user_profile.id

        if user.youtube_url and not user.profile.youtube_channel:
            channel = YoutubeChannel.query.filter_by(url=user.youtube_url).first()
            if channel is None:
                channel = YoutubeChannel(url=user.youtube_url)
            user_profile.youtube_channel_id = channel.id

        if user.twitter_url and not user.profile.twitter:
            twitter_profile = TwitterProfile.query.filter_by(url=user.twitter_url).first()
            if twitter_profile is None:
                twitter_profile = TwitterProfile(url=user.twitter_url)
            user_profile.twitter_id = twitter_profile.id

        if user.instagram_url and not user.profile.instagram:
            instagram_profile = InstagramProfile.query.filter_by(url=user.instagram_url).first()
            if instagram_profile is None:
                instagram_profile = InstagramProfile(url=user.instagram_url)
            user_profile.instagram_id = instagram_profile.id

        if user.facebook_url and not user.profile.facebook:
            facebook_profile = FacebookUser.query.filter_by(url=user.facebook_url).first()
            if facebook_profile is None:
                facebook_profile = FacebookUser(url=user.facebook_url)
            user_profile.facebook_user_id = facebook_profile.id

    def update_social_media_url(self, usr: SlapsUser, url_element, progress_bar: tqdm = None):
        """
        Assigns the user's social media url with a url element input. The inputs text will determine what's assigned..
        :param usr: The user to update.
        :param url_element: The element containing the url.
        :param progress_bar: The progress bar to update. (Optional)
        """
        url = url_element.text
        if 'youtube' in url:
            usr.youtube_url = url
            self.debug(f"{usr.username} -> Updated Youtube", progress_bar=progress_bar)
        elif 'twitter' in url:
            usr.twitter_url = url
            self.debug(f"{usr.username} -> Updated Twitter", progress_bar=progress_bar)
        elif 'instagram' in url:
            usr.instagram_url = url
            self.debug(f"{usr.username} -> Updated Instagram", progress_bar=progress_bar)
        elif 'facebook' in url:
            usr.facebook_url = url
            self.debug(f"{usr.username} -> Updated Facebook", progress_bar=progress_bar)

    def prepare_user_to_message(self, user: SlapsUser, retrying=False, on_user_page=False, progress_bar: tqdm = None):
        """
        By preparing to message the user we navigate to their profile,
        assure that we're following them (it's a requirement on slaps)
        and we also execute a quick scrape of their profile to get other information for potential user later.
        """

        # Whether or not we're skipping wait times.
        if self.config['messaging']['wait_times']["wait_skip"] is True and SlapsUser.has_sent_message(user=user, days=
        self.config['messaging']['wait_times']["days_to_wait"],
                                                                                                      hours=self.config[
                                                                                                          'messaging'][
                                                                                                          'wait_times'][
                                                                                                          "hours_to_wait"]):
            return False, f"Skipping as we messaged {user.username} in the past {self.config['messaging']['wait_times']['days_to_wait']} days"

        # Check whether or not we message them if we're already following.
        if user.following_on_slaps is True and self.config['messaging']["only_message_if_not_following"] is True:
            self.debug(f"Already following {user.username} and configured to not msg followed users.")
            return False,

        # verification request

        if not on_user_page and self.driver.current_url is not user.profile_url:
            try:
                self.driver.get(user.profile_url)
            except:
                return False, f"Over 30s when loading page @ {user.profile_url}"
            # self.scroll_down_with_key_press()

            if self.handle_creditcard_renewal_menu():
                self.debug("Credit card renewal menu detected, closing", progress_bar=progress_bar)

            if self.has_error_page():
                return False, "Error 223 when loading user page"

            if self.handle_alert_dialog():
                return False, "Alert dialog present when opening."

        if self.check_for_user_not_found_element():
            user.delete(commit=True)
            return False, f"User element not found on page for {user.username}"

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
            return False, f"Unable to locate follow button for {user.username}"

        username = self.driver.find_element(By.XPATH, SlapBotXpaths.USER_PAGE_USERNAME_ELEMENT.value)
        username = username.text.strip()

        if user.username is not username and 'not available' not in username:
            user.username = username
            user.save(commit=True)

        try:
            social_media_links = WebDriverWait(self.driver, timeout=3).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_SOCIAL_MEDIA_LINKS.value)
                )
            )
            for link in social_media_links:
                self.update_social_media_url(user, link)

            self.debug(f" ~ Updated social media profiles for {user.username}")
        except Exception as e:
            pass

        try:
            bio = WebDriverWait(self.driver, timeout=3).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_BIO_TEXT.value)
                )
            )
            self.scroll_into_view(bio)
            user.description = bio.text.strip()

            self.debug(f" ~ Updated bio for {user.username}")

        except:
            pass

        if user.joined_date is None:
            try:
                joined_date = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, SlapBotXpaths.USER_PAGE_JOIN_DATE_TEXT.value)
                    )
                )
                user.joined_date = joined_date.text.strip()
                self.debug(f" ~ Found join date {user.username}")

            except:
                pass

        play_count_total = 0
        try:
            play_count_total = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located(
                    (By.XPATH, SlapBotXpaths.USER_PAGE_PLAY_COUNT.value)
                )
            )
            user.play_count = int(play_count_total.text.strip().replace(",", ""))
            self.debug(f" ~ Updated play count for {user.username}")

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

        button_text = follow_button.text

        already_following = False

        if button_text == "Following":
            if user.following_on_slaps is False:
                self.debug(f"Updated user who we were following: {user.username}")
                user.following_on_slaps = True
                user.save(commit=True)

            # If we're only messaging users who we're NOT following, and this user is being followed already than we're skipping them.
            if self.config['messaging']["only_message_if_not_following"] is True:
                already_following = True

                if user.message_url is not None:
                    return False, f"Already following {user.username}, skipping."

        elif button_text == "Follow":
            self.scroll_into_view(follow_button)
            follow_button.click()
            user.following_on_slaps = True
            user.save(commit=True)
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
                user.save(commit=True)

        except Exception as e:
            return False, "Unable to find message button"

        if track_count > 0:
            successive_scrolls = 0
            while True:
                if successive_scrolls >= track_count:
                    self.debug(f"~ Collecting track data from {user.username} loaded page", fg="cyan")
                    break
                try:
                    end_of_posts = WebDriverWait(self.driver, 1).until(
                        EC.presence_of_element_located('//div[@style="height:100px;text-align:center;"]')
                    )
                    break
                except:
                    successive_scrolls += 1
                    self.scroll_with_javascript(700)
                    pass

            try:
                slap_song_containers = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, '//div[contains(@class,"slapPlayerContainer")]'))
                )

                self.debug(f"~ Found {len(slap_song_containers)} tracks for {user.username}", fg="cyan")

                for container in slap_song_containers:
                    player_box = container.find_element(By.XPATH, './/div[@class="playerBox"]')
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
                        track_title = player_box.find_element(By.XPATH, './/div[contains(@title,"title")]').text.strip()
                        artwork_url = player_box.find_element(By.XPATH,
                                                              './/img[@class="slapWaveArtwork"]').get_attribute('src')
                        media_url = player_box.find_element(By.XPATH,
                                                            './/div[@class="slapWaveform"]/audio').get_attribute(
                            'src')
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

                                if self.config['tag_filter_enabled'] is True and tag_name not in self.config[
                                    'tag_filter']:
                                    continue

                                tag = Tag.get_or_create(tag=tag_name)
                                tags.append(tag)
                        except:
                            pass

                        self.debug(f"~ Found {len(tags)} tags for {track_title}", fg="cyan")

                    except:
                        continue

                    try:
                        spotify_url = player_box.find_element(By.XPATH, './/a[@title="spotify"]').get_attribute('href')

                        if "artist" in spotify_url:
                            spotify_artist = SpotifyArtist.query.filter_by(url=spotify_url).first()

                            if spotify_artist is None:
                                spotify_artist = SpotifyArtist(url=spotify_url)
                                spotify_artist.save(commit=False)

                            if user.profile is None:
                                user.profile = UserProfile(slaps_user_id=user.id)
                                user.save(commit=True)

                            user.profile.spotify = spotify_artist
                            user.profile.save(commit=False)

                        elif "track" in spotify_url:
                            spotify_track = SpotifyTrack.query.filter_by(url=spotify_url).first()

                            if spotify_track is None:
                                spotify_track = SpotifyTrack(url=spotify_url)
                                spotify_track.save(commit=False)

                            if user.profile is not None and user.profile.spotify:
                                spotify_track.artist = user.profile.spotify
                                spotify_track.save(commit=False)
                    except:
                        pass

                    self.debug(f" ~ Processing track {track_title} by {user.username} @ {track_url}", fg="yellow")
                    upload = SlapsUserUpload.query.filter_by(track_url=track_url).first()

                    if upload is None:
                        upload = SlapsUserUpload(track_url=track_url, user_id=user.id, track_title=track_title,
                                                 media_url=media_url,
                                                 artwork_url=artwork_url, description=track_description, tags=tags)
                        upload.save(commit=False)

                self.debug(f" ~ Found {len(slap_song_containers)} tracks by {user.username}")
            except:
                pass

        try:
            recently_active_header = self.driver.find_elements(By.XPATH,
                                                               SlapBotXpaths.USER_PAGE_TOP_POST_HEADER.value)[0]
            self.scroll_into_view(recently_active_header)
            recent_text = recently_active_header.text.strip().lower()

            recently_active = False
            if 'min ago' in recent_text or 'hours ago' in recent_text or 'days ago' in recent_text or 'yesterday' in recent_text:
                recently_active = True

            user.recently_posted = recently_active

            if self.config['messaging']["check_recently_active"] is True:
                if recently_active is True:
                    return True, f"Prep. Success - {user.username} is active:: {recent_text}"
                return False, "Prep. Failed - User is not active."
        except:
            pass

        return True, "Preparation Successful"

    def has_error_page(self):
        try:
            error_page = WebDriverWait(self.driver, timeout=2).until(
                EC.visibility_of_element_located(
                    (By.XPATH, SlapBotXpaths.ERROR_PAGE_XPATH.value)
                )
            )
            if "Error code:" in self.driver.page_source:
                return True

            self.error_page = False
            return False
        except:
            try:
                if "Error code:" in self.driver.page_source:
                    return True
                else:
                    return False
            except:
                return False

    def handle_alert_dialog(self):
        """
        If there's an open alert dialog then we need to close it.
        This happens when Slaps is putting us to sleep for a bit.
        """
        try:
            alert_dialog = WebDriverWait(self.driver, timeout=5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, SlapBotXpaths.ALERT_DIALOG_BUTTON_CLOSE_XPATH.value)
                )
            )
            alert_dialog.click()
            return True
        except:
            pass
        return False

    def update_message_history(self, cli_bar, user, threads):
        """
        Update a users SlapsDirectMessage history based on the items that have been handed to it.
        """
        self.debug(f'Updating {user.username} Messages (sent) History with {len(threads)} items:', progress_bar=cli_bar)
        for message in threads:
            soup = BeautifulSoup(message.get_attribute('innerHTML'), 'lxml')
            dm = SlapsDirectMessage(user=user, message=soup.get_text(), timestamp=datetime.datetime.now())
            dm.save(commit=True)

        self.debug(f"Updated sent message history for {user.username}", progress_bar=cli_bar)

    def has_sent_similar_message(self, user, message, similarity_max=0.75):
        """
        Check if in all of the history between this user we've sent them a user similar to this one!
        (Easier to check all history than just last one, often times.)
        """
        if len(user.messages) == 0:
            return False

        msg_links = utils.extract_urls(message)
        for msg in user.messages:
            if self.config['messaging']["ignore_duplicate_links"] is False and utils.message_contains_any_links(
                    msg.message,
                    msg_links):
                self.debug(f"Found similar message in history for {user.username} - {msg.message}")
                return True

            if jellyfish.jaro_winkler_similarity(msg.message, message) >= similarity_max:
                self.debug(f"Found similar message in history for {user.username} - {msg.message}")
                return True

        return False

    def generate_direct_message_with_ai(self, user, cli_bar):
        """
        Generate a direct message to a user using the AI model.
        """
        self.debug(f"Generating message for {user.username}", progress_bar=cli_bar)

        direct_message_prompts = self.config['ai_prompts']['direct_message']
        if len(direct_message_prompts) == 0:
            raise Exception("No direct message prompts found in config! (ai_prompts.direct_message")

        if len(direct_message_prompts) == 1:
            prompt = direct_message_prompts[0]
        else:
            prompt = random.choice(direct_message_prompts)

        prompt_parsed = utils.generate_comment_using_spintax(text=prompt, tags_to_query=self.config['descriptive_tags'],
                                                             author_name=user.username)
        self.debug(f" ~ Communicating with AI to generate response..")
        try:
            try:
                comment = self.chat_gpt_api.generate_text_from_prompt_with_context(prompt_parsed, system_role=
                self.config['chat_gpt_prompts']['system_context'])
            except Exception as e:
                self.debug(f"~ AI failed to generate response, trying again in an hours time..")
                raise Exception("AI Failed to generate response", e)

            if self.is_invalid_ai_message(message=comment):
                return None
        except:
            traceback.print_exc()
            return self.generate_direct_message_with_ai(user, cli_bar)
        self.debug(f" ~ Generated message:\n----------------\n\n {comment['message']}")
        return comment.replace("<", "").replace(">", "").replace("\\", "")

    def generate_song_comment_with_ai(self, user, song_title):
        """
        Generate a song comment using the AI model.
        """
        self.debug(f"Generating song comment for {user.username} - {song_title}")

        song_comment_prompts = self.config['ai_prompts']['song_comment']
        if len(song_comment_prompts) == 0:
            return None

        if len(song_comment_prompts) == 1:
            prompt = song_comment_prompts[0]
        else:
            prompt = random.choice(song_comment_prompts)

        if '[song]' in prompt:
            prompt = prompt.replace('[song]', song_title)

        prompt_parsed = utils.generate_comment_using_spintax(text=prompt, tags_to_query=self.config['descriptive_tags'],
                                                             author_name=user.username)

        self.debug(f" ~ Communicating with AI to generate response..")
        time.sleep(5)
        comment = self.chat_gpt_api.generate_text_from_prompt(prompt=prompt_parsed)
        if self.is_invalid_ai_message(message=comment):
            return None
        self.debug(f" ~ Generated comment:\n----------------\n\n {comment}")
        return comment.replace("<", "").replace(">", "").replace("\n", "").replace("\\", "")

    def process_song_in_message(self, user: SlapsUser, message: str, cli_bar: tqdm = None) -> str:
        _return_message = message

        if user.uploads is None or len(user.uploads) == 0:
            self.debug(" ~ No uploads found for user, skipping song replacement", progress_bar=cli_bar)
            return _return_message
        if "[latestsong]" in _return_message:
            latest_upload: SlapsUserUpload = user.uploads.order_by(
                SlapsUserUpload.upload_date.desc()).first()
            _return_message = _return_message.replace("[latestsong]", latest_upload.track_title)
            self.debug(f" ~ Replaced [latestsong] with {latest_upload.track_title} for {user.username}",
                       progress_bar=cli_bar)

        if "[song]" in _return_message:
            random_upload: SlapsUserUpload = random.choice(user.uploads)
            _return_message = _return_message.replace("[song]", random_upload.track_title)
            self.debug(f" ~ Replaced [song] with {random_upload.track_title} for {user.username}",
                       progress_bar=cli_bar)

        return _return_message

    def execute_message(self, user: SlapsUser, retry=False, message=None, cli_bar: tqdm = None,
                        on_messaging_page=False) -> bool:
        """
        Executing a message involves the following logic:
            - Checking if the current page is the inboxing web page
                * Handle all load logic & other checks for blocks
            - Navigate to the users messaging thread, or create one if none exists.
            - Generate & Send the message to them
                * All checks such as duplication, wait times, etc. happen here.
        """
        wait_days = int(self.config['messaging']['wait_times']['days_to_wait'])
        wait_hours = int(self.config['messaging']['wait_times']['hours_to_wait'])
        if SlapsUser.has_sent_message(user=user, days=wait_days, hours=wait_hours):
            self.debug(f"~ Skipping {user.username} to not spam them, attempting to find new user")
            return self.execute_message(user=SlapsUser.get_random_unmessaged_user(days=wait_days, hours=wait_hours),
                                        message=message, cli_bar=cli_bar,
                                        on_messaging_page=on_messaging_page)

        _message = message
        cli_bar = cli_bar if cli_bar is not None else tqdm(total=1, desc=f"Sending Message to {user.username}")
        if _message is not None and self.has_sent_similar_message(user=user, message=_message):
            self.debug(f'~ Skipping {user.username} to not spam them, choosing a new user')
            return self.execute_message(user=SlapsUser.get_random_unmessaged_user(days=wait_days, hours=wait_hours),
                                        message=message, cli_bar=cli_bar,
                                        on_messaging_page=on_messaging_page)

        # Inboxing is when we're iterating ONLY the inbox (and don't change the page)
        # This checks if we need to load the URL
        if self.driver.current_url is not user.message_url:
            try:
                # self.debug(f"Navigating to message {user.username}")
                self.debug(f"Navigating to message {user.username}", progress_bar=cli_bar)
                try:
                    self.driver.get(user.message_url)
                except:
                    return False
            except:
                # self.debug("Unable to navigate to user message link")
                # self.debug(f'Unable to navigate to {user.username} message link @ {user.message_url}')
                self.debug(f'Unable to navigate to {user.username} message link @ {user.message_url}',
                           progress_bar=cli_bar)
                return False

            if self.handle_creditcard_renewal_menu():
                self.debug("Credit card renewal menu detected, closing")

            if self.has_error_page():
                self.debug(f"Error page 223 skipping user {user.username}", progress_bar=cli_bar)
                self.error_page = True
                return False

            # Finish waiting for the page to load
            try:
                self.debug(f'Awaiting Page Load of {user.username}', progress_bar=cli_bar)

                loading_symbol_not_there = WebDriverWait(self.driver, 120).until(
                    EC.invisibility_of_element_located(
                        (By.XPATH, SlapBotXpaths.INBOX_PAGE_LOADING_ELEMENT.value)
                    )
                )
            except:
                self.debug(f"Loading symbol still visible after 2 minutes for {user.username} at {user.message_url}",
                           progress_bar=cli_bar)
                return False

        if retry is True:
            if self.driver.current_url is not user.message_url:
                self.driver.get(user.message_url)
                # Finish waiting for the page to load
                try:
                    self.debug(f'Awaiting Page Load of {user.username}', progress_bar=cli_bar)

                    loading_symbol_not_there = WebDriverWait(self.driver, 300).until(
                        EC.invisibility_of_element_located(
                            (By.XPATH, SlapBotXpaths.INBOX_PAGE_LOADING_ELEMENT.value)
                        )
                    )
                except:
                    self.debug(
                        f"Loading symbol still visible after 5 minutes for {user.username} at {user.message_url} while retrying",
                        progress_bar=cli_bar)
                    return False

            if self.handle_creditcard_renewal_menu():
                self.debug("Credit card renewal menu detected, closing", progress_bar=cli_bar)

            if self.has_error_page():
                self.debug(f"Error page 223 skipping user {user.username}")
                self.debug(f"Error page 223 skipping user {user.username}", progress_bar=cli_bar)
                return False

        # todo revise messaging logic.

        if self.handle_alert_dialog():
            self.debug(f"Alert dialog present, unable to execute message on {user.username}", progress_bar=cli_bar)
            return False

        try:
            self.debug(f"Looking for message box on {user.username}", progress_bar=cli_bar)
            message_box = WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located(
                    (By.XPATH,
                     SlapBotXpaths.INBOX_PAGE_MESSAGE_TEXTAREA.value)
                )
            )


        except:
            self.debug(f"Unable to locate message box on page of {user.username}", progress_bar=cli_bar)
            # self.debug(f"Unable to locate message box on page of {user.username}")
            return False

        # Force message history updating.
        all_messages_sent = self.driver.find_elements(By.XPATH,
                                                      SlapBotXpaths.INBOX_PAGE_ALL_MESSAGES_SENT.value)
        self.debug(f"Updating message history for {user.username} with {len(all_messages_sent)} sent previously",
                   progress_bar=cli_bar)
        self.update_message_history(cli_bar, user, all_messages_sent)

        # todo check for last reply.

        messages_received = []

        most_recent_reply = ""
        most_recent_reply_id = 0

        self.debug(f"Looking for messages received from {user.username}", progress_bar=cli_bar)
        try:
            messages_received_non_bulk = self.driver.find_elements(By.XPATH,
                                                                   SlapBotXpaths.INBOX_PAGE_MESSAGE_RECEIVED_NON_BULK.value)

            messages_received_bulk = self.driver.find_elements(By.XPATH,
                                                               SlapBotXpaths.INBOX_PAGE_MESSAGE_RECEIVED_BULK.value)

            _messages_received = messages_received_non_bulk + messages_received_bulk
            for message in _messages_received:
                _msg_id = int(message.get_attribute("id"))

                text = message.find_element(By.XPATH, SlapBotXpaths.INBOX_PAGE_MESSAGE_RECEIVED_MESSAGE_TEXT.value).text
                msg_model = SlapsDirectMessage.query.filter_by(message_id=f"{_msg_id}").first()
                if msg_model is None:
                    msg_model = SlapsDirectMessage(user=user, message_id=f"{_msg_id}", message=text, received=True)
                    msg_model.save(commit=True)
                if _msg_id > most_recent_reply_id:
                    most_recent_reply_id = int(f"{_msg_id}")
                    most_recent_reply = message.find_element(By.XPATH,
                                                             SlapBotXpaths.INBOX_PAGE_MESSAGE_RECEIVED_MESSAGE_TEXT.value).text

        except:
            traceback.print_exc()
            self.debug(f" ~ Error when trying to get messages received from {user.username}", progress_bar=cli_bar)
            pass

        # Generate message
        if _message is None:
            self.debug(f"~ Generating message for {user.username}", progress_bar=cli_bar)

            if self.config['comment_settings']['use_openai'] or self.config['comment_settings']['use_chat_gpt']:
                if most_recent_reply != "" and most_recent_reply_id > 0:
                    self.debug(f" ~ Most recent reply from {user.username} is {most_recent_reply}",
                               progress_bar=cli_bar)
                    _message = self.generate_reply_to_direct_message_with_ai(user=user, reply=most_recent_reply)

                else:
                    _message = self.generate_direct_message_with_ai(user=user, cli_bar=cli_bar)
            else:
                #
                #
                # _random_message = random.choice(self.config['direct_messages'])
                # _message = self.process_song_in_message(user=user, message=_random_message)
                #
                # if "[latestsong]" in _message or "[song]" in _message:
                #     while "[latestsong]" in _message or "[song]" in _message:
                #         _random_msg = random.choice(self.config['direct_messages'])
                #         _message = self.process_song_in_message(user=user, message=_random_msg)

                _message = utils.generate_comment_using_spintax(text=random.choice(self.config['direct_messages']),
                                                                tags_to_query=self.config['descriptive_tags'],
                                                                author_name=user.username)

        if self.has_sent_similar_message(user=user, message=_message):
            self.debug(f'~ Skipping {user.username} to not spam them')
            return False

        try:
            self.driver.execute_script(f"messageFocus();")
        except:
            traceback.print_exc()
            self.debug("Unable to focus message box for sending message to {user.username}")
            return False

        time.sleep(random.randint(3, 6))

        # escape string
        _message = _message.replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r").replace('"', '\\"')

        try:
            self.driver.execute_script(f"$('.typeMessage').text('{_message}');")
            time.sleep(random.randint(3, 6))
        except Exception as e:
            traceback.print_exc()
            self.debug(f"Unable to send write message \"{_message}\". Check for unescaped strings.",
                       progress_bar=cli_bar)
            # self.debug(f"Unable to locate message box on page of {user.username}")
            return False

        try:
            if self.config['debug']:
                input("Press enter to send message")
            self.driver.execute_script("inboxSendMessage();")
        except:
            traceback.print_exc()
            self.debug(f"Unable to send message to {user.username} via button or pure javascript invocation")
            return False

        time.sleep(random.randint(5, 10))

        if self.handle_alert_dialog():
            return False

        return True

    def handle_cookie_consent(self) -> bool:
        """
        Accept cookies if the cookie consent modal is visible.
        """
        try:
            cookie_modal = WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, '//*[contains(@class,"cookieModalConfirmButton")]')
                )
            )

            cookie_modal.click()
            return True
        except:
            return False

    def handle_creditcard_renewal_menu(self, close=True) -> bool:
        """
        Dertermine whether or not the credit carc renewal modal (menu) has been displayed on the page & close it.
        :param close:
        :return: True if it was closed or false if not.
        """
        try:
            cc_modal = WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, '//i[contains(@class,"fa fa-times pointer") and @onclick="closeCcModal();"]')
                )
            )

            if not close:
                return True

            cc_modal.click()
        except:
            return False

    def has_error_retrieving_conversation(self, close=True) -> bool:
        """
        Determine whether or not the 'Error getting this conversation' dialog is visible on the screen.
        :param close:
        :return:
        """
        pass

    def is_inboxing_page_loading(self):
        """
        Determine whether or not the inboxing page is loading.
        The loading symbol will be invisible if it's done loading.
        """
        # Make sure the loading symbol is no longer present.

        if '/messages/' not in self.driver.current_url:
            raise Exception("Invalid page. Not on inboxing page. Navigate to slaps messaging and retry this logic.")

        try:
            loading_symbol_not_there = WebDriverWait(self.driver, 600).until(
                EC.invisibility_of_element_located(
                    (By.XPATH, '//div[@id="messageHere"]//i[@class="fa fa-circle-o-notch fa-spin fa-fw"]')
                )
            )
            return True
        except:
            return False

    def get_and_create_users_from_inboxing_page(self, retry=False, progress_bar: tqdm = None) -> List[int]:
        """
        Get all users from the inboxing page and create them in the database if they don't exist.
        """

        if ActionLog.updated_within_range("slapbot_inboxing_userids", 8):
            self.debug(f"Loading inboxing users from cache", progress_bar=progress_bar)
            previously_collected_users = json.loads(ActionLog.get("slapbot_inboxing_userids", []).value)

            if len(previously_collected_users) > 0:
                return previously_collected_users
            else:
                pass

        if '/messages/' not in self.driver.current_url:
            self.driver.get('https://www.distrokid.com/messages/')

            if self.is_inboxing_page_loading():
                self.debug("Waiting for inboxing page to load (Indexing users for messaging)",
                           progress_bar=progress_bar)
                sleep_time = self.get_random_messaging_sleep_time()
                time.sleep(sleep_time)
                return self.get_and_create_users_from_inboxing_page(retry=retry, progress_bar=progress_bar)

        valid_users = 0
        user_thread_elements = self._retrieve_user_threads()
        total_user_threads = len(user_thread_elements)
        user_ids: List[int] = []

        def get_info_from_element(message_thread):
            try:
                user_uuid = message_thread.get_attribute("useruuid")
                user_username = message_thread.get_attribute("username")

                return user_uuid, user_username
            except:
                raise

        for message_thread in user_thread_elements:
            user_uuid = None
            user_username = None

            # If we've already entered retry here then break out after it fails a second time.
            # This logic is to prevent stale elements being checked.
            if retry is True:
                try:
                    user_uuid, user_username = get_info_from_element(message_thread)
                except:
                    break
            else:
                try:
                    user_uuid, user_username = get_info_from_element(message_thread)
                except:
                    return self.get_and_create_users_from_inboxing_page(retry=True, progress_bar=progress_bar)

            user = SlapsUser.query.filter_by(message_url=f"https://distrokid.com/messages/?to={user_uuid}").first()

            if user is None:
                user = SlapsUser(username=user_username, message_url=f"https://distrokid.com/messages/?to={user_uuid}",
                                 following_on_slaps=True)
                user.save(commit=True)
                self.debug(
                    f"[{valid_users} valid / {total_user_threads} total] Created {user.username} due to lack of record",
                    progress_bar=progress_bar)

            elif user.message_url is None:

                user.message_url = f"https://distrokid.com/messages/?to={user_uuid}"
                user.save(commit=True)

                self.debug(
                    f"[{valid_users} valid / {total_user_threads} total] + {user.username} => message_url assigned {user.message_url}",
                    progress_bar=progress_bar)

            elif user.username != user_username and jellyfish.jaro_winkler_similarity(user.username,
                                                                                      user_username) > 0.8:

                user.username = user_username
                user.save(commit=True)
                self.debug(
                    f"[{valid_users} valid / {total_user_threads} total] + {user.username} => username assigned {user_username}",
                    progress_bar=progress_bar)

            valid_users += 1
            user_ids.append(user.id)
            self.debug(f"[{valid_users} valid / {total_user_threads} total] + {user.username}",
                       progress_bar=progress_bar)

        ActionLog.log("slapbot_inboxing_userids", json.dumps(user_ids))  # update so we can cache things.
        ScraperLog.get_or_create(url=self.driver.current_url, collected_user_count=len(user_ids), user_ids=user_ids)
        return user_ids

    def _retrieve_user_thread(self, user: SlapsUser):
        """
        Retrieve a user thread from the inboxing page via their uuid. UUID is parsed from
        """
        try:
            user_thread = WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, f'//div[@useruuid="{user.message_url.split("?to=")[1]}"]')
                )
            )
            return user_thread
        except:
            return None

    def _retrieve_user_threads(self):
        """
        Inline function to retrieve user threads.

        Reduces repetitive code.
        """
        try:
            _user_threads = self.driver.find_elements(By.XPATH, '//div[contains(@class,"myThread")]')
            return _user_threads

            # return _user_threads if not self.config['messaging']['inboxing_reverse_order'] else reversed(_user_threads)
        except:
            return []

    def get_random_unmessaged_user(self, user_ids: List[int]) -> SlapsUser | None:
        """
        Inline function to retrieve a random unmessaged user.
        """
        users_from_homepage = SlapsUser.query.filter(SlapsUser.id.in_(user_ids)).all()

        user_selection_attempts_max = len(users_from_homepage)
        iterations = 0
        while user_selection_attempts_max > iterations:
            iterations += 1

            user = random.choice(users_from_homepage)

            if user.message_url is None:
                continue

            if user.following_on_slaps is False:
                continue

            if len(user.messages) > 0:
                continue

            # Check wait skipping
            if self.config['messaging']['wait_times']["wait_skip"] is False and SlapsUser.has_sent_message(user,
                                                                                                           days=int(
                                                                                                               self.config[
                                                                                                                   'messaging'][
                                                                                                                   'wait_times'][
                                                                                                                   "days_to_wait"]),
                                                                                                           hours=int(
                                                                                                               self.config[
                                                                                                                   'messaging'][
                                                                                                                   'wait_times'][
                                                                                                                   "hours_to_wait"])):
                continue

            msg = utils.generate_comment_using_spintax(text=random.choice(self.config['direct_messages']),
                                                       author_name=user.username,
                                                       tags_to_query=self.config['descriptive_tags'])
            if self.has_sent_similar_message(user=user, message=msg):
                self.debug(
                    f'Sent {user.username} a similar message to generated message. Skipping')
                continue

            return user

        return None

    def generate_reply_to_direct_message_with_ai(self, user, reply) -> str:
        """
        Write a reply to a message in the inbox using Chat GPT
        """
        prompts = self.config['ai_prompts']['direct_messaging_reply']
        random_reply = random.choice(prompts) if len(prompts) > 1 else prompts[0]
        _msg = random_reply.replace('[reply]', reply)
        prompt = utils.generate_comment_using_spintax(text=_msg, author_name=user.username,
                                                      tags_to_query=self.config['descriptive_tags'])
        _message_data = self.chat_gpt_api.send_message(prompt)
        if 'message' not in _message_data.keys():
            return None

        _message = _message_data['message'].replace("<", ">")
        if self.is_invalid_ai_message(_message):
            return None

        return _message

    _invalid_message_list = ["I'm not sure what you mean", "sorry"]

    def is_invalid_ai_message(self, message) -> bool:
        if message is None:
            return True

        if any(_s in message for _s in self._invalid_message_list):
            return True

        return False

    def generate_unsent_direct_message(self, user: SlapsUser) -> str:
        """
        Get a message to send to the user that has not been sent to them before.
        (Not using AI currently)
        """
        message_to_send = None
        for message in self.config['direct_messages']:
            try:
                # todo implement chatgpt prompt writing reply
                _message = utils.generate_comment_using_spintax(text=message, author_name=user.username,
                                                                tags_to_query=self.config['descriptive_tags'])
            except Exception as e:
                msg = traceback.format_exc()
                self.debug(msg)
                self.debug(f"Failed to generate message for {user.username}.")
                continue

            # todo implement time checking (day waiting / hour waiting) & optional duplicate linking.

            if self.has_sent_similar_message(user=user, message=_message,
                                             similarity_max=self.config['messaging']['similarity_limit']):
                continue

            message_to_send = _message
            break

        return message_to_send

    _messaged_ids = set()

    def perform_inboxing(self, cli_bar=None, user: SlapsUser = None, existing_conversations=False) -> bool:
        """
        Performs the "Inboxing" feature of Slapbot, where each user who hasn't been messaged recently will be messaged.
        """
        cli_bar = tqdm() if cli_bar is None else cli_bar

        if self.handle_creditcard_renewal_menu():
            self.debug("Credit card renewal menu detected, closing.", progress_bar=cli_bar)

        self.debug(f"Awaiting page load", progress_bar=cli_bar)
        try:
            loading_symbol_not_there = WebDriverWait(self.driver, timeout=500).until(
                EC.invisibility_of_element_located(
                    (By.XPATH, SlapBotXpaths.INBOX_PAGE_LOADING_ELEMENT.value)
                )
            )

        except:
            return False

        if existing_conversations is True:
            if "/messages" not in self.driver.current_url:
                self.driver.get("https://www.distrokid.com/messages/")
                self.debug(f"Waiting for inboxing page to load (Indexing users for messaging)", progress_bar=cli_bar)

            self.debug(f"Page loaded- Retrieving user_ids to message", progress_bar=cli_bar)

            # todo iterate all items on the website matching the xpath
            user_conversation_elements_xpath = "//div[contains(@class,'myThread') and contains(@onclick,'threadClick')]"

            try:
                user_conversation_elements = WebDriverWait(self.driver, timeout=600).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, user_conversation_elements_xpath)
                    )
                )
                self.debug(f"Retrieved {len(user_conversation_elements)} user conversation elements from inboxing page",
                           progress_bar=cli_bar)
            except Exception as e:
                traceback.print_exc()
                # raise Exception("Unable to retrieve user conversation elements from inboxing page")
                return False

            # Build all the information of users from the conversations we've had on the platform.
            users_to_message_first = []

            if ActionLog.updated_within_range("slapbox_inboxing_existing_conversations_list", hours_ago=12):

                users_to_message_first = json.loads(
                    ActionLog.get("slapbox_inboxing_existing_conversations_list", []).value)
                if type(users_to_message_first) is str:
                    users_to_message_first = users_to_message_first.replace("[", "").replace("]", "").replace(" ",
                                                                                                              "").split(
                        ',')
            else:
                self.debug(f"Retrieving users to message first from inboxing page", progress_bar=cli_bar)

                for conversation_thread in user_conversation_elements:
                    """
                    TODO:
                    1. Get user uuid from element
                    2. Check if user in database
                    3. If not, create user in database & save
                    4. Post processing, can message the users- Always best to archive first
                    """

                    user_uuid = conversation_thread.get_attribute("useruuid")
                    user_username = conversation_thread.get_attribute("username")
                    message_url = f"https://distrokid.com/messages/?to={user_uuid}"

                    slaps_user = SlapsUser.query.filter(
                        or_(SlapsUser.message_url == message_url, SlapsUser.username == user_username,
                            SlapsUser.profile_url == f"https://slaps.com/{user_username}")).first()

                    if slaps_user is None:
                        self.debug(f"Creating user {user_username} with message url {message_url}",
                                   progress_bar=cli_bar)
                        slaps_user = SlapsUser(username=user_username, message_url=message_url,
                                               profile_url=f"https://slaps.com/{user_username}",
                                               following_on_slaps=False)
                        slaps_user.save(commit=True)

                    users_to_message_first.append(slaps_user.id if type(slaps_user.id) is int else int(slaps_user.id))
                    self.debug(f"Added {slaps_user.username} to users to message first", progress_bar=cli_bar)

                ActionLog.log("slapbox_inboxing_existing_conversations_list", users_to_message_first)

                self.debug(f"Cached {len(users_to_message_first)} users in conversation list",
                           progress_bar=cli_bar)

            if self.config['messaging']['inboxing_reverse_order']:
                users_to_message_first = reversed(users_to_message_first)
                self.debug(f"Reversed order of users to message first", progress_bar=cli_bar)

            for user_id in users_to_message_first:
                slaps_user = SlapsUser.query.filter_by(id=user_id).first()

                if slaps_user is None:
                    continue

                if slaps_user.message_url is None:
                    self.debug(f"Skipping {slaps_user.username} due to lack of message url", progress_bar=cli_bar)

                if not SlapsUser.has_sent_message(user=slaps_user, days=7):
                    user = slaps_user
                    break

        # Retrieve users that we can message from the last iteration of our caches user-ids
        if user is None:
            # try:
            #     user_ids_to_message: List[int] = self.get_and_create_users_from_inboxing_page(progress_bar=cli_bar)
            #     random_user = SlapsUser.query.filter_by(id=random.choice(user_ids_to_message)).first()
            #     if random_user.id in self._messaged_ids:
            #         while random_user.id in self._messaged_ids:
            #             if self.config['messaging']['wait_times']['wait_skip'] is False and SlapsUser.has_sent_message(
            #                     user=random_user, days=self.config['messaging']['wait_times']['days_to_wait'],
            #                     hours=self.config['messaging']['wait_times']['hours_to_wait']):
            #                 continue
            #         random_user = SlapsUser.query.filter_by(id=random.choice(user_ids_to_message)).first()
            #
            # except:
            #     traceback.print_exc()
            #     raise Exception("Double check that you've logged in, and re-run the script.")
            random_user = SlapsUser.get_random_unmessaged_user(
                days=int(self.config['messaging']['wait_times']['days_to_wait']),
                hours=int(self.config['messaging']['wait_times']['hours_to_wait']))

            if random_user is None:
                self.debug("No users to message, sleeping for 1 hour")
                ActionLog.log("timestamp_slapbot_inboxing_finish",
                              value=datetime.datetime.utcnow().timestamp() + 3600)
                ActionLog.log("slaps_inboxing_sleep_time", 3600)
                self.sleeping_after_messaging = True
                return False
            user_ids_to_message = [random_user.id]
        else:
            random_user = user
            user_ids_to_message = [user.id]

        if self.config['comment_settings']['use_chat_gpt']:
            msg = self.generate_direct_message_with_ai(user=random_user, cli_bar=cli_bar)
        elif self.config['comment_settings']['use_openai']:
            pass
        else:
            # _random_msg = random.choice(self.config['direct_messages'])
            # _random_msg = self.process_song_in_message(user=random_user, message=_random_msg)
            # if "[latestsong]" in _random_msg or "[song]" in _random_msg:
            #     while "[latestsong]" in _random_msg or "[song]" in _random_msg:
            #         _random_msg = random.choice(self.config['direct_messages'])
            #         _random_msg = self.process_song_in_message(user=random_user, message=_random_msg)
            msg = utils.generate_comment_using_spintax(text=random.choice(self.config['direct_messages']),
                                                       author_name=random_user.username,
                                                       tags_to_query=self.config['descriptive_tags'])

        if msg is None:
            return False

        if not self.execute_message(user=random_user, message=msg):
            self.debug(f"Unable to send message to {random_user.username}")

            if self.handle_alert_dialog():
                self.debug("There's an alert dialog stopping you from messaging. Sleeping until it's gone",
                           progress_bar=cli_bar, println=True)
                sleep_time = random.randint(self.config['error_failsafe']['sleep_min'],
                                            self.config['error_failsafe']['sleep_max'])
                self.debug(f"Sleeping for {sleep_time}s", progress_bar=cli_bar, println=True)
                ActionLog.log("slaps_inboxing_sleep_time", sleep_time)
                ActionLog.log("timestamp_slapbot_inboxing_finish",
                              value=datetime.datetime.utcnow().timestamp() + sleep_time)
                self.sleeping_after_messaging = True
                return False

            # sleep_time = self.get_random_messaging_sleep_time()
            # ActionLog.log("slaps_inboxing_sleep_time", sleep_time)
            # ActionLog.log("timestamp_slapbot_inboxing_finish",
            #               value=datetime.datetime.utcnow().timestamp() + sleep_time)
            # self.sleeping_after_messaging = True
            return False

        self.total_messaged_users_count += 1
        sleep_time = self.get_random_messaging_sleep_time()
        self.debug(
            f"[{len(user_ids_to_message)} total | {self.total_messaged_users_count} msgs] Messaged {random_user.username} - Sleeping for {sleep_time}s")
        ActionLog.log("timestamp_slapbot_inboxing_finish", value=datetime.datetime.utcnow().timestamp() + sleep_time)
        ActionLog.log("slaps_inboxing_sleep_time", sleep_time)
        self.sleeping_after_messaging = True
        self._messaged_ids.add(random_user.id)
        return True

    def check_if_user_exists(self, user: SlapsUser, cli_bar: tqdm = None):
        assert user is not None

        if user.profile_url is None:
            return False

        self.debug(f"Performing request to {user.username} profile page: {user.profile_url}", progress_bar=cli_bar)
        profile_contents_request = requests.get(user.profile_url)

        self.debug(f"Request complete - Parsing contents of {user.username} profile page @ {user.profile_url}",
                   progress_bar=cli_bar)
        soup = BeautifulSoup(profile_contents_request.content, 'lxml')
        not_exists_text_element = soup.select_one('div.slapColumnContainer div.playerBox')
        if not_exists_text_element is None:
            return True

        _txt = not_exists_text_element.text.strip()
        if "This user doesn't exist" in _txt:
            return False

        return True

    def slap_users_songs(self):
        """
        Slap the users song!
        """
        try:
            pass
        except:
            pass
        pass

    def get_leads_from_database(self, unfollowed=True):
        _following_on_slaps = not unfollowed
        users = SlapsUser.query.filter(SlapsUser.following_on_slaps == _following_on_slaps).all()
        return users

    def message_random_lead(self, cli_bar=None, unfollowed=True) -> bool:
        """
        Message a random lead from the database.
        :param cli_bar: Progress bar to update
        :param unfollowed: Whether or not to message unfollowed leads
        """

        cli_bar = cli_bar if cli_bar is not None else tqdm()

        _following_on_slaps = not unfollowed

        if float(ActionLog.get("timestamp_slaps_unfollowed_leads_cache_refresh",
                               0).value) < datetime.datetime.utcnow().timestamp():
            leads_ids = []

            self.debug(f"Indexing users leads from database (following {unfollowed})... This may take some time.")

            users_in_query = SlapsUser.query.filter(SlapsUser.following_on_slaps == _following_on_slaps).all()
            for user in users_in_query:
                message = self.generate_unsent_direct_message(user=user)

                if message is None:
                    continue

                leads_ids.append(user.id)

            ActionLog.log("slaps_unfollowed_leads_cache", value=leads_ids)
            ActionLog.log("timestamp_slaps_unfollowed_leads_cache_refresh",
                          value=datetime.datetime.utcnow().timestamp() + 3600)

        leads_ids = json.loads(ActionLog.get("slaps_unfollowed_lead_ids", []).value)
        if len(leads_ids) == 0:
            self.debug("No leads in cache.")
            unfollowed_leads = self.get_leads_from_database(unfollowed=unfollowed)

            # unfollowed_leads = self.scrape_users_from_slaps_homepage(sort="new")
            # unfollowed_leads += self.scrape_users_from_slaps_homepage(sort="hot")

            for user in unfollowed_leads:
                leads_ids.append(user.id)

            ActionLog.log("slaps_unfollowed_lead_ids", value=leads_ids)
            self.debug(
                f"Found {len(leads_ids)} unfollowed leads after cache update with database unfollowed leads.")
            # return False

        random_user: SlapsUser = SlapsUser.query.filter_by(id=random.choice(leads_ids)).first()

        # Nobody random
        if random_user is None:
            return False

        while SlapsUser.has_sent_message(user=random_user, days=14) or self.config[
            'username'] in random_user.username.lower():
            random_user: SlapsUser = SlapsUser.query.filter_by(id=random.choice(leads_ids),
                                                               following_on_slaps=_following_on_slaps).first()

            if random_user is None:
                return False

            if random_user.profile_url is None:
                continue

        while not self.check_if_user_exists(random_user):
            try:
                self.debug(f"Deleting {random_user.username} as they literally don't exist anymore.")

                random_user.delete(commit=True)
            except:
                pass
            leads_ids.remove(random_user.id)
            random_user = SlapsUser.query.filter_by(id=random.choice(leads_ids)).first()

            if random_user is None:
                return False

            if self.config[
                'username'] in random_user.username.lower():
                continue

            if not self.config['messaging']['wait_times']["wait_skip"] \
                    and SlapsUser.has_sent_message(user=random_user,
                                                   days=self.config['messaging']['wait_times']["days_to_wait"],
                                                   hours=self.config['messaging']['wait_times']["hours_to_wait"]):
                continue

        if self.config['user_scraping']['followers_and_following']:
            self.debug(f'Scraping information from {random_user.username} pages (followers & following)')
            self.scrape_users_from_users_pages(random_user, cli_bar=cli_bar)

        self.debug(f'Preparing to message {random_user.username}', progress_bar=cli_bar)

        status, message = None, None
        try:
            status, message = self.prepare_user_to_message(random_user)
        except Exception as e:
            traceback.print_exc()
            self.debug(f"~ Skipped {random_user.username}: {e}", progress_bar=cli_bar)
            return False

        if not status:
            self.debug(f"~ Skipped {random_user.username}: {message}", progress_bar=cli_bar)
            return False

        unable_to_message_due_to_error_223 = False
        if not self.execute_message(cli_bar=cli_bar, user=random_user):
            # check if we've got an error page!!
            if self.error_page is True:
                sleep_time = self.get_error_failsafe_sleep_time()
                ActionLog.log("slaps_unfollowed_leads_sleep_time", sleep_time)
                ActionLog.log('timestamp_slaps_message_leads_sleep_finish',
                              value=datetime.datetime.utcnow().timestamp() + sleep_time)
                return False

            return self.message_random_lead(cli_bar=cli_bar)

        sleep_time = self.get_message_leads_sleep_time()

        ActionLog.log("slaps_unfollowed_leads_sleep_time", sleep_time)
        ActionLog.log("timestamp_slaps_message_leads_sleep_finish",
                      value=datetime.datetime.utcnow().timestamp() + sleep_time)
        self.total_messaged_users_count += 1
        self.debug(f"Messaged {random_user.username} successfully. Sleeping for {sleep_time}s", progress_bar=cli_bar)
        return True

    def filter_user_list(self, collected_data: List[SlapsUser]):
        """
        Filters the user list to remove users
        """
        wait_days = int(self.config['messaging']['wait_times']['days_to_wait'])
        wait_hours = int(self.config['messaging']['wait_times']['hours_to_wait'])
        if self.config['messaging']['wait_times']['wait_skip'] is False:
            non_recent = set(user for user in collected_data if
                             SlapsUser.has_sent_message(user=user, days=wait_days,
                                                        hours=wait_hours) is False)
            non_recent = list(non_recent)
            return non_recent
        return collected_data

    def get_error_failsafe_sleep_time(self):
        return random.randint(self.config['error_failsafe']['sleep_min'],
                              self.config['error_failsafe']['sleep_max'])

    def get_message_leads_sleep_time(self):
        return random.randint(self.config['message_leads']['sleep_min'],
                              self.config['message_leads']['sleep_max'])

    def get_homepage_scrape_sleep_time(self):
        if 'sleep_min' not in self.config['user_scraping'].keys():
            raise Exception(
                f"Configuration is missing 'sleep_min' key in 'user_scraping' section.\n\n{pprint.pformat(self.config)}")

        if 'sleep_max' not in self.config['user_scraping'].keys():
            raise Exception(
                f"Configuration is missing 'sleep_max' key in 'user_scraping' section.\n\n{pprint.pformat(self.config)}")
        try:
            return random.randint(self.config['user_scraping']['sleep_min'],
                                  self.config['user_scraping']['sleep_max'])
        except:
            raise Exception(
                "Error getting sleep time for user scraping. Check your config file. Min in 'user_scraping' is higher than max")

    def is_logged_in(self) -> bool:
        try:
            element = WebDriverWait(self.driver, timeout=30).until(
                EC.presence_of_element_located((By.XPATH, '//a[@id="slapNavMe"]')))

            if self.config['username'].lower() in element.get_attribute('href').lower():
                self.debug(f"Logged in as {self.config['username']}!", progress_bar=None, fg="green")
                return True
            else:
                self.debug(f"Unable to confirm login.")
                input("Login & Press Enter to continue...")
                return False
        except:
            return False

    def find_song_on_page_and_comment(self, progress_bar: tqdm = None) -> tuple[bool, str]:
        """Find a song on the page and comment on it. Use AI to generate a comment tailored to the user"""

        # todo find bug where the song title isn't found or the author is someonen else.
        try:
            has_songs_on_page, tracks_on_page = self.has_song_available_on_page_for_commenting()
            while not has_songs_on_page:
                self.debug(f" ~ Loading more songs.. ", progress_bar=progress_bar)
                self.send_keypress_to_page(key=Keys.END,
                                           count=random.randint(self.config['song_commenting']['scroll_min'],
                                                                self.config['song_commenting']['scroll_max']))
                has_songs_on_page, tracks_on_page = self.has_song_available_on_page_for_commenting()

        except:
            traceback.print_exc()
            self.debug(f" ~ Unable to find song on page. ", progress_bar=progress_bar)
            return False, "No songs on page"

        if len(tracks_on_page) == 0:
            return False, "No songs on page"

        slaps_comment_search_iteration_count = 0

        # look for

        for _player_box in tracks_on_page:
            selected_song_author_name = None
            selected_song_comment_textarea = None

            # todo select random part of the song to comment on

            try:
                selected_song_comment_textarea = _player_box.find_element(By.XPATH,
                                                                          ".//textarea[contains(@class,'slapCommentInputRoot')]")
            except:
                raise Exception("Could not find song id on page element")

            try:
                selected_author_profile_url_element = _player_box.find_element(By.XPATH,
                                                                               ".//span//a[contains(@onclick,'return slapCheckLogin();')][1]")
                selected_song_author_profile_url = selected_author_profile_url_element.get_attribute('href')
            except:
                raise Exception(f"Unable to get profile url from playerBox")

            try:
                selected_song_author_name = selected_author_profile_url_element.text
            except:
                raise Exception(f"Unable to get author name from playerBox on {selected_song_author_name}")

            if selected_song_author_name is not None and selected_song_author_name.lower() == self.config[
                'username'].lower():
                self.debug(f" ~ Skipping song because it was posted by me", progress_bar=progress_bar)
                selected_slaps_user = None
                selected_song_author_name = None
                selected_song_comment_textarea = None
                selected_song_author_profile_url = None
                selected_song_title = None
                _player_box = None
                continue

            self.debug(
                f"~ Looking for {selected_song_author_name}'s data in database via profile url {selected_song_author_profile_url}",
                progress_bar=progress_bar)
            selected_slaps_user = SlapsUser.query.filter_by(profile_url=selected_song_author_profile_url).first()

            if selected_slaps_user is None:
                selected_slaps_user = SlapsUser.query.filter_by(username=selected_song_author_name).first()

                if selected_slaps_user is None:
                    selected_slaps_user = SlapsUser(profile_url=selected_song_author_profile_url,
                                                    username=selected_song_author_name)
                    selected_slaps_user.save(commit=True)
                    self.debug(f"~ Added {selected_slaps_user.username} to database")
                else:
                    self.debug(f"~ Found {selected_slaps_user.username} in database via username")
            else:
                self.debug(
                    f"~ Found {selected_slaps_user.username} in database via playerBox element on {selected_song_author_name}")

            if selected_slaps_user is None:
                raise Exception(
                    f"Unable to find {selected_song_author_name} (profile_url={selected_song_author_profile_url} in database")
            elif selected_slaps_user.username != selected_song_author_name or selected_slaps_user.profile_url != selected_song_author_profile_url:
                self.debug(
                    f" ~ User found via player box has an anomaly. Re assigning based on correct variables. {selected_slaps_user.username} != {selected_song_author_name}")
                selected_slaps_user = SlapsUser.query.filter_by(username=selected_song_author_name).first()

                if selected_slaps_user is None:
                    selected_slaps_user = SlapsUser.query.filter_by(
                        profile_url=selected_song_author_profile_url).first()

                if selected_slaps_user is None:
                    try:
                        selected_slaps_user = SlapsUser(profile_url=selected_song_author_profile_url,
                                                        username=selected_song_author_name)
                        selected_slaps_user.save(commit=True)
                    except:
                        selected_slaps_user = SlapsUser.query.filter_by(
                            profile_url=selected_song_author_profile_url).first()
                        if selected_slaps_user is None:
                            raise Exception(
                                f"Unable to find {selected_song_author_name} (profile_url={selected_song_author_profile_url} in database")

                        self.debug(
                            f" ~ Found {selected_slaps_user.username} in database via profile url {selected_song_author_profile_url} not matching expected username / profile url: {selected_song_author_name} @ {selected_song_author_profile_url}")
                        selected_slaps_user.username = selected_song_author_name
                        selected_slaps_user.save(commit=True)
                        self.debug(f" ~ Updated {selected_slaps_user.username} in database with correct username")

            selected_song_title = _player_box.find_element(By.XPATH, ".//div[@title='Song title']").text

            if selected_song_title is None:
                slaps_comment_search_iteration_count += 1
                selected_slaps_user = None
                selected_song_author_name = None
                selected_song_comment_textarea = None
                selected_song_author_profile_url = None
                selected_song_title = None
                _player_box = None
                continue

            if SlapsComment.has_commented_on(selected_slaps_user, selected_song_title):
                self.debug(
                    f" ~ {selected_slaps_user.username} has already commented on {selected_song_title}. Skipping..",
                    progress_bar=progress_bar)
                slaps_comment_search_iteration_count += 1
                selected_slaps_user = None
                selected_song_author_name = None
                selected_song_comment_textarea = None
                selected_song_author_profile_url = None
                selected_song_title = None
                _player_box = None
                continue

            if selected_song_author_name != selected_slaps_user.username:
                _proper_slaps_user: SlapsUser = SlapsUser.query.filter_by(username=selected_song_author_name).first()

                if _proper_slaps_user is None:
                    _proper_slaps_user = SlapsUser.query.filter_by(profile_url=selected_song_author_profile_url).first()
                    _proper_slaps_user.username = selected_song_author_name
                    _proper_slaps_user.save(commit=True)

                if _proper_slaps_user is None:
                    self.debug(
                        f" ~~ Creating {selected_song_author_name} in database. Profile url is {selected_song_author_profile_url}")
                    _proper_slaps_user = SlapsUser(username=selected_song_author_name,
                                                   profile_url=selected_song_author_profile_url)
                    _proper_slaps_user.save(commit=True)

                self.debug(
                    f" ~ Found {selected_slaps_user.username} in database via playerBox element on {selected_song_author_name} - {selected_song_title} but {selected_song_author_name} != {selected_slaps_user.username}")
                if _proper_slaps_user.profile_url != selected_song_author_profile_url:
                    self.debug(
                        f" ~ Found {_proper_slaps_user.username} in database profile url {_proper_slaps_user.profile_url} :: {selected_song_author_profile_url} // {selected_song_author_name}")
                    selected_song_author_name = _proper_slaps_user.username
                    selected_song_author_profile_url = _proper_slaps_user.profile_url

                selected_slaps_user = _proper_slaps_user

            if SlapsComment.has_commented_on(user=selected_slaps_user, title=selected_song_title):
                self.debug(
                    f" ~ Already commented on song {selected_song_title} by {selected_slaps_user.username}. Skipping.. ",
                    progress_bar=progress_bar)
                slaps_comment_search_iteration_count += 1
                selected_slaps_user = None
                selected_song_author_name = None
                selected_song_comment_textarea = None
                selected_song_author_profile_url = None
                selected_song_title = None
                _player_box = None
                continue

            if SlapsUser.has_commented(selected_slaps_user, days=self.config['messaging']['wait_times']['days_to_wait'],
                                       hours=self.config['messaging']['wait_times']['hours_to_wait']):
                slaps_comment_search_iteration_count += 1
                self.debug(f"~ Commented on {selected_slaps_user.username} too recently. Skipping..",
                           progress_bar=progress_bar)
                selected_slaps_user = None
                selected_song_author_name = None
                selected_song_comment_textarea = None
                selected_song_author_profile_url = None
                selected_song_title = None
                _player_box = None

                continue

            if selected_song_author_name != selected_slaps_user.username:
                raise Exception(f"Username mismatch: {selected_song_author_name} != {selected_slaps_user.username}")

            self.debug(
                f" ~ Selected song {selected_song_title} by {selected_song_author_name} (user={selected_slaps_user.username}) ({selected_song_author_profile_url}) for commenting")

            try:
                wave_element = _player_box.find_element(By.XPATH, './/wave[@class="slapOuterWave"]')
                region_element = wave_element.find_element(By.XPATH, './/region[@class="wavesurfer-region"]')
                self.scroll_into_view(region_element)
                region_element.click()
            except:
                pass

            self.scroll_into_view(selected_song_comment_textarea, center=True)
            time.sleep(random.randint(1, 2))
            break
            # Give it some flame

        if selected_song_comment_textarea is None:
            return False, "No comment box textarea found"

        if selected_slaps_user is None:
            return False, 'No suitable poster found. Likely commented on all recents'

        # interact with sound player

        needs_comment = True
        song_comment = None
        while needs_comment is True:
            try:
                # Todo generate comment
                if self.config['comment_settings']['use_chat_gpt'] or self.config['comment_settings']['use_openai']:
                    song_comment = self.generate_song_comment_with_ai(user=selected_slaps_user,
                                                                      song_title=selected_song_title)

                else:
                    song_comment = utils.generate_comment_using_spintax(text=random.choice(self.config['comments']),
                                                                        tags_to_query=self.config['descriptive_tags'],
                                                                        author_name=selected_slaps_user.username,
                                                                        song_title=selected_song_title)
                if song_comment is None:
                    return False, "Unable to generate comment"

                needs_comment = False
            except:
                traceback.print_exc()

        if self.handle_creditcard_renewal_menu():
            self.debug("Credit card renewal menu detected, closing")

        self.debug(
            f"~ Commenting on {selected_slaps_user.username}'s song {selected_song_title} with comment {song_comment}")

        try:
            selected_song_comment_textarea.click()
        except:
            try:
                sign_in_link = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//a[contains(text(),"Sign in with DistroKid")]')))
                sign_in_link.click()
                return self.find_song_on_page_and_comment(progress_bar=progress_bar)
            except:
                traceback.print_exc()
                return False, "Unable to click comment box"

        try:
            time.sleep(random.randint(1, 3))
            if self.driver_type == DriverType.UNDETECTED_CHROME or self.driver_type == DriverType.CHROME:
                try:
                    song_comment = song_comment.replace('"', '\\"').replace("'", "\\'")
                    self.set_text_via_javascript(selected_song_comment_textarea, song_comment)
                except:
                    traceback.print_exc()
                    return False, "Unable to set text via javascript"
            else:
                try:
                    selected_song_comment_textarea.send_keys(song_comment)
                except:
                    try:
                        self.set_text_via_javascript(selected_song_comment_textarea, song_comment)
                    except:
                        traceback.print_exc()
                        return False, "Unable to set text via javascript or keys."
            time.sleep(random.randint(1, 3))

            if self.config['debug'] is True:
                input(f"Press enter to continue...")
            selected_song_comment_textarea.send_keys(Keys.ENTER)
            time.sleep(random.randint(3, 8))

            selected_slaps_user.comment(comment=song_comment, title=selected_song_title)

            if self.config['song_liking']['enabled'] is True and self.config['song_liking'][
                'like_chance'] > random.randint(1, 100):
                try:
                    self.debug(f" ~ Giving song some flame to {selected_song_title}.. ", progress_bar=progress_bar)
                    slaps_fire_button = _player_box.find_element(By.XPATH,
                                                                 './/div[contains(@class,"slapFireLongPress")]')
                    self.scroll_into_view(slaps_fire_button)

                    for i in range(random.randint(1, 50)):
                        slaps_fire_button.click()
                        time.sleep(random.uniform(0.1, 0.5))
                except:
                    pass

                try:
                    if self.config['song_liking']['love_chance'] > random.randint(1, 100):
                        favorite_button = _player_box.find_element(By.XPATH,
                                                                   './/div[contains(@onclick,"slapFavorite")]')
                        self.scroll_into_view(favorite_button)
                        favorite_button.click()
                except KeyError:
                    self.debug(f" ~ Could not find favorite button for {selected_song_title}.. ",
                               progress_bar=progress_bar)
                    pass

            return True, "Posted"
        except:
            traceback.print_exc()
            return False, "Unable to post comment (unknown error)"

    def get_slaps_user_from_player_box(self, player_box: WebElement) -> SlapsUser:
        try:
            selected_author_profile_url_element = player_box.find_element(By.XPATH,
                                                                          ".//span//a[contains(@onclick,'return slapCheckLogin();')][1]")
            selected_song_author_profile_url = selected_author_profile_url_element.get_attribute('href')
        except:
            raise

        try:
            selected_song_author_name = selected_author_profile_url_element.text
        except:
            raise Exception(f"Unable to get author name from playerBox on {selected_song_author_profile_url}")

        slaps_user = SlapsUser.query.filter_by(profile_url=selected_song_author_profile_url).first()

        if slaps_user is None:
            slaps_user = SlapsUser(profile_url=selected_song_author_profile_url, username=selected_song_author_name)
            slaps_user.save(commit=True)

        return slaps_user

    def has_song_available_on_page_for_commenting(self) -> tuple[bool, list[WebElement] | None]:
        """Whether or not there is a song available for commenting on the page"""
        song_id = None

        self.scroll_up_with_key_press()

        try:
            player_boxes = WebDriverWait(self.driver, timeout=30).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class,'playerBox')]")))
            self.debug(f"Found {len(player_boxes)} player boxes on page.")
        except:
            raise

        _usable_elements = []

        for player_box in player_boxes:
            try:
                song_comment_element = player_box.find_element(By.XPATH,
                                                               ".//textarea[contains(@class,'slapCommentInputRoot')]")
            except:
                click.secho(f"Unable to find slapCommentInputRoot on playerBox @ {self.driver.current_url}", fg="red")
                raise

            try:
                song_title = player_box.find_element(By.XPATH,
                                                     ".//div[@class='slapSongTitleContainer']//div[@title='Song title']").text
            except:
                click.secho(f"Unable to find songTitle on playerBox @ {self.driver.current_url}", fg="red")
                raise

            user = self.get_slaps_user_from_player_box(player_box=player_box)
            self.debug(f"Found song title {song_title} to interact with by user {user.username}")

            if SlapsComment.has_commented_on(user=user, title=song_title):
                self.debug(
                    f"~ {user.username} has already been commented on for song {song_title} :: HAS_SONG_AVAILABLE")
                continue

            _usable_elements.append(player_box)

        if len(_usable_elements) == 0:
            return False, None
        return True, _usable_elements

    def begin(self):
        """
        Bot Logic as as follow:
            1. Navigate to slaps.com
            2. Collect a list of users (and some information on them).
            3. Follow these users & flame their tracks (pressing the corresponding buttons)
            4. Send these users a message about playlists on Spotify (free) all they have to do is let me know they're interested and we can talk!
            5.
        :return:
        """
        if not self.setup_complete or self.driver is None:
            self.startup(config_file_name=self.config_file_name, driver_type=self.driver_type)
            print("Startup logic has been executed")
        else:
            print("Setup complete previously")

        self.driver.get("http://slaps.com/")

        if self.handle_cookie_consent():
            self.debug("Cookie consent detected & closed")

        if self.has_to_login or self.driver_type == DriverType.UNDETECTED_CHROME:
            input("Press any key after you've logged in to your slaps account...")
            # In browsers where sessions are saved, we will not need to login again.
            while not self.is_logged_in():
                input("Try Again:: Press any key after you've logged in to your slaps account...")
            if self.driver_type is not DriverType.UNDETECTED_CHROME:
                self._config['has_to_login'] = False
                utils.save_json_file(self.config_file_name, self._config)
        # Begin smart looping!
        progress_bar = tqdm()
        sleep_since_iteration = 0
        if self.config['smart_loop']['enabled'] is True:
            while self.config['smart_loop']['enabled'] is True:
                # Manage all sleep times (if any) before doing anything else.

                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get('timestamp_slaps_comment_song_sleep_finish', 0).value):
                    if self.sleeping_after_song_comment is True:
                        self.debug(f"Finished sleeping after song comment. Continuing...", progress_bar=progress_bar)
                    self.sleeping_after_song_comment = False
                else:
                    self.sleeping_after_song_comment = True

                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get("timestamp_slapbot_inboxing_finish", 0).value):
                    if self.sleeping_after_messaging is True:
                        self.debug(f"~ Finished sleeping after messaging, continuing...", progress_bar=progress_bar)

                    self.sleeping_after_messaging = False
                else:
                    self.sleeping_after_messaging = True

                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get("timestamp_slaps_message_leads_sleep_finish", 0).value):
                    if self.sleeping_after_leads is True:
                        self.debug(f"~ Finished sleeping after messaging unfollowed leads, continuing...",
                                   progress_bar=progress_bar)
                    self.sleeping_after_leads = False

                else:
                    self.sleeping_after_leads = True

                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get("timestamp_homepage_scrape_sleep_finish", 0).value):
                    if self.sleeping_after_homepage_scrape is True:
                        self.debug(f"~ Finished sleeping after homepage scrape, continuing...",
                                   progress_bar=progress_bar)
                    self.sleeping_after_homepage_scrape = False
                else:
                    self.sleeping_after_homepage_scrape = True

                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get("timestamp_slaps_message_scraped_leads_sleep_finish", 0).value):
                    if self.sleeping_after_messaging_scraped_lead is True:
                        self.debug(f"~ Finished sleeping after messaging scraped leads, continuing...",
                                   progress_bar=progress_bar)
                    self.sleeping_after_messaging_scraped_lead = False
                else:
                    self.sleeping_after_messaging_scraped_lead = True

                # Comment on songs to build CTR, landing on the front page of slaps.
                # COMMENT ON SONG

                if self.config['song_commenting']['enabled'] is True and (
                        self.sleeping_after_song_comment is False or self.config['song_commenting'][
                    'sleep_after_comment'] is False):
                    self.debug("Preparing to comment on a song..", progress_bar=progress_bar)
                    if self.handle_creditcard_renewal_menu():
                        self.debug(f"Successfully handled credit card renewal menu", progress_bar=progress_bar)
                    if 'https://slaps.com/?action=&id=&sort=' in self.driver.current_url:
                        self.send_keypress_to_page(count=random.randint(3, 10))
                    else:

                        try:
                            self.driver.get(
                                f"https://slaps.com/?action=&id=&sort={self.config['song_commenting']['sort_by']}")
                        except:
                            self.debug("Failed to navigate to slaps.com", progress_bar=progress_bar)
                            continue

                    self.debug(
                        f"Successfully navigated to slaps.com/?action=&id=&sort={self.config['song_commenting']['sort_by']}",
                        progress_bar=progress_bar)
                    self.debug(f"Finding song & commenting...", progress_bar=progress_bar)
                    status, message = self.find_song_on_page_and_comment(progress_bar=progress_bar)
                    if not status:
                        sleep_since_iteration = 0
                        self.debug(f"Failed to find a song to comment on:: {message}", progress_bar=progress_bar)
                        if self.config['debug']:
                            input("Press any key to continue...")
                        continue
                    sleep_since_iteration = 0

                    sleep_time = random.randint(self.config['song_commenting']['sleep_min'],
                                                self.config['song_commenting']['sleep_max'])
                    ActionLog.log("timestamp_slaps_comment_song_sleep_finish",
                                  datetime.datetime.utcnow().timestamp() + sleep_time)
                    ActionLog.log("timestamp_slaps_comment_song_sleep_amount", sleep_time)
                    self.sleeping_after_song_comment = True

                # Inbox a random user who hasn't been messaged recently.
                if not self.sleeping_after_messaging and self.config['messaging'][
                    'inbox_existing_conversations'] is True:
                    self.driver.get("https://www.distrokid.com/messages")
                    self.debug(f"Loaded inboxing page for existing conversations", progress_bar=progress_bar)
                    if self.perform_inboxing(cli_bar=progress_bar, existing_conversations=True):
                        sleep_since_iteration = 0

                # Message a random unfollowed user
                if not self.sleeping_after_leads and self.config['message_leads'][
                    'enabled'] is True:
                    self.debug("Preparing to message a random unfollowed lead...", progress_bar=progress_bar)
                    sleeping_time = self.get_message_leads_sleep_time()

                    message_unfollowed = self.config['message_leads']['unfollowed']

                    message_followed = self.config['message_leads']['followed']

                    # Determine by random if we're going to message unfollowed or followed leads if both are enabled.
                    if message_unfollowed and message_followed:
                        message_unfollowed = random.randint(1, 2) == 1
                    elif not message_unfollowed and not message_followed:
                        self.debug(
                            f"You forgot to set 'unfollowed' and 'followed' in 'message_leads' for slapbot config. Choosing at random")
                        message_unfollowed = random.randint(1, 2) == 1
                    elif message_followed and not message_unfollowed:
                        message_unfollowed = False

                    if not self.message_random_lead(cli_bar=progress_bar, unfollowed=message_unfollowed):
                        self.debug(f"~ Unable to message unfollowed leads.", progress_bar=progress_bar)
                    else:
                        self.debug("Finished messaging a random unfollowed lead...", progress_bar=progress_bar)
                    ActionLog.log("timestamp_slaps_message_leads_sleep_finish",
                                  value=datetime.datetime.utcnow().timestamp() + sleeping_time)
                    time.sleep(5)

                # Scrape homepage & message users from there (at a pace)
                if not self.sleeping_after_messaging_scraped_lead and self.config['user_scraping'][
                    'enabled'] is True:
                    collected_user_ids = json.loads(ActionLog.get("slaps_recently_scraped_users", []).value)
                    self.debug(f"Loaded {len(collected_user_ids)} from cache..", progress_bar=progress_bar)

                    # Collect a list of users from the homepage if we haven't already done so recently.
                    if not ActionLog.updated_within_range("slaps_recently_scraped_users",
                                                          hours_ago=self.config['user_scraping'][
                                                              'hours_to_wait']) or len(collected_user_ids) == 0:
                        self.debug(f"Preparing to collect users from homepage...", progress_bar=progress_bar)
                        collected_data = []
                        if self.config['user_scraping']['hot_tab'] is True:
                            collected_data += self.scrape_users_from_slaps_homepage(sort="hot")

                        if self.config['user_scraping']['new_tab'] is True:
                            collected_data += self.scrape_users_from_slaps_homepage(sort="new")

                        if len(collected_data) > 0:
                            collected_data = self.filter_user_list(collected_data=collected_data)
                            collected_user_ids = [user.id for user in collected_data if not user.following_on_slaps]
                            ActionLog.log("slaps_recently_scraped_users", value=collected_user_ids)
                        else:
                            self.debug("No new leads were found, sleeping before trying again...",
                                       progress_bar=progress_bar)

                        sleep_time = self.get_homepage_scrape_sleep_time()
                        ActionLog.log("timestamp_slaps_user_scraping_finish",
                                      datetime.datetime.utcnow().timestamp() + sleep_time)
                        ActionLog.log("slaps_user_scraping_sleep_time", sleep_time)

                    self.debug(f"Collected {len(collected_user_ids)} users from scrape (or cache)",
                               progress_bar=progress_bar)

                    random_user: SlapsUser = SlapsUser.get_random_user()
                    while SlapsUser.has_sent_message(user=random_user,
                                                     days=self.config['messaging']['wait_times']['days_to_wait'],
                                                     hours=self.config['messaging']['wait_times']['hours_to_wait']):
                        random_user = SlapsUser.get_random_user()
                        self.debug(f"User {random_user.username} has been messaged recently, finding another...",
                                   progress_bar=progress_bar)
                    if self.config['user_scraping'][
                        'followers_and_following'] is True and not SlapsUser.has_deep_scraped(user=random_user, days=
                    self.config['user_scraping']['deep_scrape_days'], hours=self.config['user_scraping'][
                        'hours_to_wait']):
                        self.debug(f"Checking followers / following of {random_user.username}")
                        self.scrape_users_from_users_pages(random_user, cli_bar=progress_bar)
                        random_user.deep_scrape_completion_timestamp = datetime.datetime.utcnow()
                        random_user.save(commit=True)

                    if random_user.message_url is None:
                        self.debug(f"Navigating to profile of {random_user.username}")
                        try:
                            if self.driver.current_url != random_user.profile_url:
                                self.driver.get(random_user.profile_url)
                        except:
                            sleep_time = random.randint(1, 10)
                            self.debug(
                                f'Error when navigating to {random_user.profile_url}, sleeping for {sleep_time}s to avoid error',
                                progress_bar=progress_bar)
                            time.sleep(sleep_time)
                            continue

                        if self.handle_creditcard_renewal_menu():
                            self.debug("Credit card renewal menu detected, closing")

                        if self.has_error_page():
                            sleep_time = self.get_random_messaging_sleep_time() / 2
                            self.debug(
                                f"Error page when navigating to {random_user.username} profile page  - Retrying in {sleep_time}s",
                                progress_bar=progress_bar)
                            ActionLog.log("timestamp_slaps_message_scraped_leads_sleep_finish",
                                          value=datetime.datetime.utcnow().timestamp() + sleep_time)
                            ActionLog.log("slaps_message_scraped_leads_sleep_time", sleep_time)
                            continue

                        if not random_user.following_on_slaps:
                            self.debug(
                                f"Preparing {random_user.username} for messaging (Checking profile, following, collecting socials, etc...)",
                                progress_bar=progress_bar)

                            try:
                                status, message = self.prepare_user_to_message(random_user)
                                if status is False:
                                    self.debug(f"Skipped {random_user.username}: {message}", fg="yellow")
                                    continue
                            except Exception as e:
                                self.debug(f'Error during follow & scrape of {random_user.username}', fg="red")
                                continue

                    if self.config['user_scraping']['messaging_enabled'] is True:

                        sleep_time = self.get_messaging_scraped_lead_sleep_time()
                        if not self.execute_message(cli_bar=progress_bar, user=random_user):
                            self.debug(f"Unable to message {random_user.username}.",
                                       progress_bar=progress_bar)
                        else:
                            self.debug(f"Successfully messaged {random_user.username} - Sleeping for {sleep_time}",
                                       progress_bar=progress_bar)
                            ActionLog.log("timestamp_slaps_message_scraped_leads_sleep_finish",
                                          value=datetime.datetime.utcnow().timestamp() + sleep_time)
                            ActionLog.log("slaps_message_scraped_leads_sleep_time", sleep_time)

                # user_scraping_sleep_time = f'{float(ActionLog.get(f"slaps_user_scraping_sleep_time", 0).value)}s' if \
                #     self.config['user_scraping']['enabled'] else "N/A"
                # message_scraped_lead__sleep_time = f'{float(ActionLog.get(f"slaps_message_scraped_leads_sleep_time", 0).value)}s' if \
                #     self.config['user_scraping']['messaging_enabled'] is True else "N/A"
                # inboxing_sleep_time = f'{float(ActionLog.get(f"slaps_inboxing_sleep_time", 0).value)}s' if \
                #     self.config['messaging']['inbox_existing_conversations'] is True else "N/A"
                # unfollowed_lead_sleep_time = f'{float(ActionLog.get("slaps_unfollowed_leads_sleep_time", 0).value)}s' if \
                #     self.config['message_leads']['enabled'] is True else "N/A"
                # song_comment_sleep_time = f'{float(ActionLog.get("timestamp_slaps_comment_song_sleep_amount", 0).value)}s' if \
                #     self.config['song_commenting']['enabled'] is True else "N/A"

                self.progress_bar.set_description(f"Slept for {sleep_since_iteration}s since last interaction.")
                sleep_since_iteration += 1
                time.sleep(1)

    def get_messaging_scraped_lead_sleep_time(self):
        return random.randint(self.config['user_scraping']['messaging_sleep_min'],
                              self.config['user_scraping']['messaging_sleep_max'])
