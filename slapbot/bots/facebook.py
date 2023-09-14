"""
Intention is to Add Friends & Send messages to them to acquire Pre-Saves!

Rules to make it successful:
- No repeat messages.
- Personalize the message.
"""
import datetime
import enum
import random
import time
import traceback

import click
import jellyfish
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import func
from tqdm import tqdm
from typing import List

from slapbot.ai.chatgpt import ChatGPT3APIWrapper
from slapbot.bots import BrowserBotBase, DriverType
from slapbot import utils, db
from slapbot.models import FacebookUser, ActionLog, FacebookMessage, FacebookStatusEngagement


class FacebookLinks(enum.Enum):
    """
    Enum of Facebook links.
    """
    MY_FRIENDS = "https://mbasic.facebook.com/profile.php?v=friends"
    ADD_FRIENDS = "https://mbasic.facebook.com/friends/center/mbasic/"

    def __str__(self):
        return self.value


# Todo implement check for "You cant do this right now"
# Todo When unable to message, add friends & return trying again periodically.
# todo implement check where element //div[@title="You Can't Use This Feature Right Now"] is present after message or like
# then a 5x multiplier is applied to the wait time.

class FacebookBot(BrowserBotBase):
    MESSAGE_HISTORY_XPATHS = [
        '//div[@class="bx"]/div',
        '//div[@class="bv"]/div',
        '//div[@class="bw"]/div',
        '//div[@class="bu"]/div',
    ]

    def __init__(self, headless=None):
        super().__init__(driver_type=DriverType.FIREFOX, late_init=True,
                         headless=headless if headless is not None else False)

        self.config_file_name = "facebook_config.json"

        self._config = dict(
            sleep_min=5, # Sleep min is 5 seconds
            sleep_max=60, # Sleep max is 60 seconds
            friend_requests=dict( # Friend requests config
                enabled=False, # Whether or not to send friend requests
                request_limit=40, # How many friend requests to send per run
                request_limit_sleep_time=60 * 60 * 5, # How long to sleep after sending the max amount of friend requests
                sleep_min=60, # Minimum sleep time after sending a friend request
                sleep_max=60 * 10, # Maximum sleep time after sending a friend request
                force_indexing=False, # Whether or not to force indexing of friends (should be enabled on first run to populate DB)
            ),
            messaging=dict(
                ignore_list=['Persons Name'], # List of names to ignore when sending messages
                similarity_limit=0.85, # How similar a name can be to ignore it (see jellyfish library in for more info)
                sleep_min=60 * 3, # Minimum sleep time after sending a message
                sleep_max=60 * 15, # Maximum sleep time after sending a message
            ),
            status_engagement=dict( # Status engagement config
                enabled=False, # Whether or not to engage with statuses
                sleep_min=60, # Minimum sleep time after engaging with a status
                sleep_max=1200, # Maximum sleep time after engaging with a status
                sleep_chance=100, # Chance to sleep after engaging with a status
            ),
            chrome_profile_path=self.locate_chrome_profile(), # Path to chrome profile auto located
            firefox_profile_path=self.locate_firefox_profile(), # Path to firefox profile auto located
            # Comments to use when sending messages
            comments=[
                "[greeting] [author] Could you please pre-save my new song? pre-save link: [link]",
            ],
            # Greetings to use when sending messages
            descriptive_tags=dict(
                link=[
                    "http://skreet.ca"
                ],
                greeting=[
                    "{Hey|Yo|Hey Yo|Heyyo|Yoo}"
                ]
            ),
            smart_sleep=True, # Whether or not to use smart sleep (sleeps for a random amount of time between min and max in between actions)
            chatgpt=dict( # ChatGPT config (see slapbot.ai.chatgpt.ChatGPT3APIWrapper for more info)
                enabled=False, # Whether or not to use ChatGPT
                secret_key="", # ChatGPT secret key
                prompts={ # Prompts to use for ChatGPT
                    "direct-message": [
                        {
                            "context": "",
                            "msg": "Can you write a direct message to [author]? Tell them about my new song at [link]"
                        }
                    ]
                }
            ),
            debug={
                "testing-input": False # Whether or not to use testing input (see slapbot.ai.chatgpt.ChatGPT3APIWrapper for more info)
            }

        )

        self._chat_gpt_api: ChatGPT3APIWrapper = None

        utils.debugger.debug_silence = True

        # These two variables help keep the error pages away.
        self.sleeping_after_error_page = False
        self.timestamp_sleep_after_error_page_finish = 0

        self.force_friend_indexing = False  # FLAG from CLI to force indexing of friends.

        self.sleeping_after_friend_request = False  # Flag to indicate if we are sleeping after friend requests.
        self.timestamp_friend_request_sleep_finish = 0  # Determines when the bot can start sending friend requests again.

        self.sleeping_after_message = False
        self.timestamp_message_sleep_finish = 0  # Determines when the bot can start sending messages again.

        self.sleeping_after_like = False
        self.timestamp_sleep_after_like_finish = 0  # Determines when the bot can like again

    ERROR_PAGE_XPATH = "//h2[contains(text(),\"You Can't Use This Feature Right Now\")]"

    def has_error_page(self):
        try:
            error_page = WebDriverWait(self.driver, timeout=5).until(
                EC.presence_of_element_located(
                    (By.XPATH, FacebookBot.ERROR_PAGE_XPATH)
                )
            )
            return True
        except:
            return False

    @property
    def chat_gpt_api(self) -> ChatGPT3APIWrapper:
        if self._chat_gpt_api is None:
            self._chat_gpt_api = ChatGPT3APIWrapper()
        return self._chat_gpt_api

    def perform_smart_sleep_loop(self):
        """
        Perform the loop of adding friends & sending messages.

        Smart sleeping is enabled by default where the bot will sleep for a random amount of time between each interaction.
        """
        progress_bar = tqdm()
        sleep_since_last_interaction = 0
        sleep_check_iteration = 0
        while True:
            sleep_check_iteration += 1

            # If sleeping after liking status, check if we can like again.
            if datetime.datetime.utcnow().timestamp() > float(
                    ActionLog.get("timestamp_sleep_after_like_finish", default_value=0).value):
                if self.sleeping_after_like is True:
                    self.debug("~ Finished sleeping after like.", progress_bar=progress_bar)
                self.sleeping_after_like = False
            else:
                self.sleeping_after_like = True

            if datetime.datetime.utcnow().timestamp() > float(
                    ActionLog.get("timestamp_friend_request_sleep_finish", 0).value):
                if self.sleeping_after_friend_request is True:
                    self.debug("~ Finished sleeping after friend requests.", progress_bar=progress_bar)
                self.sleeping_after_friend_request = False
            else:
                self.sleeping_after_friend_request = True

            if datetime.datetime.utcnow().timestamp() > float(
                    ActionLog.get("timestamp_message_sleep_finish", 0).value):
                self.debug("~ Finished sleeping after messages.", progress_bar=progress_bar)
                self.sleeping_after_message = False
            else:
                self.sleeping_after_message = True

            if self.sleeping_after_like is False and self.config['status_engagement']['enabled']:
                # Find a status to like!
                self.engage_with_statuses(cli_bar=progress_bar)

                # If there's a chance to sleep, then take it.
                if random.randint(0, 100) < self.config['status_engagement']['sleep_chance']:
                    sleep_time = random.randint(self.config['status_engagement']['sleep_min'],
                                                self.config['status_engagement']['sleep_max'])
                    self.debug(f"~ Finished liking statuses - Sleeping action for {sleep_time} seconds.",
                               progress_bar=progress_bar)

                    self.sleeping_after_like = True
                    self.timestamp_sleep_after_like_finish = datetime.datetime.utcnow().timestamp() + sleep_time
                    ActionLog.log("timestamp_sleep_after_like_finish", self.timestamp_sleep_after_like_finish)
                    ActionLog.log("facebook_sleep_like_time", sleep_time)
                    sleep_since_last_interaction = 0
                else:
                    self.debug(f"~ Sleeping for 5s after liking a status", progress_bar=progress_bar)
                    time.sleep(5)

            if self.sleeping_after_error_page is True:
                if datetime.datetime.utcnow().timestamp() > float(
                        ActionLog.get("timestamp_errorpage_sleep_finish", 0).value):
                    self.sleeping_after_error_page = False
                else:
                    # progress_bar.update(sleep_since_last_interaction)
                    self.debug(
                        f"~ Slept for {sleep_since_last_interaction}/{ActionLog.get('errorpage_sleep_amount').value}s due to error page.",
                        progress_bar=progress_bar)
                    time.sleep(1)
                    sleep_since_last_interaction += 1
                    continue

            # Check again cause the value may have changed.
            if not self.sleeping_after_friend_request and self.config['friend_requests']['enabled']:
                self.debug("~ Sending friend request", progress_bar=progress_bar)
                self.add_users(message_while_sleeping=True)
                sleep_since_last_interaction = 0
                sleep_time = random.randint(self.config['friend_requests']['sleep_min'],
                                            self.config['friend_requests']['sleep_max'])

                self.debug(f"~ Finished sending friend request - Sleeping action for {sleep_time} seconds.",
                           progress_bar=progress_bar)

                self.sleeping_after_friend_request = True
                self.timestamp_friend_request_sleep_finish = datetime.datetime.utcnow().timestamp() + sleep_time
                ActionLog.log("timestamp_friend_request_sleep_finish", self.timestamp_friend_request_sleep_finish)
                ActionLog.log("facebook_sleep_friend_time", sleep_time)

            if not self.sleeping_after_message and self.config['messaging']['enabled']:
                # self.debug("~ Preparing to send message", progress_bar=progress_bar)
                friend, message = self.get_first_valid_random_friend_and_message(progress_bar=progress_bar)

                if friend is None:
                    self.debug("~ No valid friends to message - Reindexing.", progress_bar=progress_bar)
                    self.index_friends_list_for_database()
                    continue

                if not self.execute_message(friend, message, progress_bar=progress_bar):
                    self.debug(f"~ Not sending message to {friend.name}", progress_bar=progress_bar)
                else:
                    sleep_time = random.randint(self.config['messaging']['sleep_min'],
                                                self.config['messaging']['sleep_max'])
                    self.debug(f"~ Messaged {friend.name}",
                               progress_bar=progress_bar)
                    self.sleeping_after_message = True
                    self.timestamp_message_sleep_finish = datetime.datetime.utcnow().timestamp() + sleep_time
                    ActionLog.log("timestamp_message_sleep_finish", self.timestamp_message_sleep_finish)
                    ActionLog.log("facebook_sleep_message_time", sleep_time)
                    sleep_since_last_interaction = 0

            # progress_bar.update(sleep_since_last_interaction)
            self.debug(f"~ Slept for {sleep_since_last_interaction}s since last interaction.",
                       progress_bar=progress_bar)
            time.sleep(1)
            sleep_since_last_interaction += 1

    def get_random_sleep_time(self):
        return random.randint(self.config['sleep_min'], self.config['sleep_max'])

    def get_unsent_message(self, user: FacebookUser) -> str:
        """
        Get a message to send to the user that has not been sent to them before.
        """
        message_to_send = None
        if self.config['chatgpt']['enabled'] is True:
            direct_message_prompt_obj = random.choice(self.config['chatgpt']['prompts']['direct-message'])
            dm_prompt = direct_message_prompt_obj['msg']

            prompt_text = utils.generate_comment_using_spintax(text=dm_prompt,
                                                               tags_to_query=self.config['descriptive_tags'],
                                                               author_name=user.name.split(" ")[0])
            message_to_send = self.chat_gpt_api.generate_text_from_prompt(prompt_text)
            self.debug(f"Generated message using chatgpt: {message_to_send}")
            return message_to_send
        else:

            for i in range(len(self.config['comments'])):
                try:
                    _message = utils.generate_comment_using_spintax(text=random.choice(self.config['comments']),
                                                                    tags_to_query=self.config['descriptive_tags'],
                                                                    author_name=user.name.split(" ")[0])
                except Exception as e:
                    msg = traceback.format_exc()
                    self.debug(msg)
                    self.debug(f"Failed to generate message for {user.name}.")
                    continue

                # todo implement time checking (day waiting / hour waiting) & optional duplicate linking.

                if user.check_message_history(message=_message,
                                              similarity_max=self.config['messaging']['similarity_limit'],
                                              ignore_duplicate_links=False):
                    continue

                message_to_send = _message
                break

        return message_to_send

    def get_first_valid_random_friend_and_message(self, progress_bar: tqdm):
        """
        Get the first user to message (and the message to send to them)

        Will return Tuple(None,None) if there's nobody to message.
        """
        friends: List[FacebookUser] = FacebookUser.query.filter_by(ignore=False).all()

        unmessaged_friends = list()
        for friend in friends:
            if len(friend.messages) == 0:
                unmessaged_friends.append(friend)

        if len(unmessaged_friends) == 0:
            unmessaged_friends = friends
            click.secho(f"~ No new users to message. Sending messages to existing users.", fg="yellow")
        random.shuffle(unmessaged_friends)

        friends_to_message = []

        for friend in unmessaged_friends:

            # Get the first message we can send to the user.
            message_to_send = self.get_unsent_message(friend)

            if message_to_send is None:
                self.debug(f"~ No message to send to {friend.name}: They've received all currently available messages.",
                           progress_bar=progress_bar)
                continue

            if len(self.config['messaging']['ignore_list']) > 0 and friend.name in self.config['messaging'][
                'ignore_list']:
                friend.ignore = True
                friend.save(commit=True)
                continue

            if friend.ignore is None:
                friend.ignore = False
                friend.save(commit=True)

            # First message users that we have not messaged before.
            if len(friend.messages) == 0:
                return friend, message_to_send

            if friend.ignore is True:
                self.debug(f"~ Ignoring {friend.name}", progress_bar=progress_bar)
                continue

            friends_to_message.append(friend.id)

        if len(friends_to_message) > 0:
            friend = FacebookUser.get_by_id(random.choice(friends_to_message))  # get random user.
            message = self.get_unsent_message(friend)

            if message is None:
                raise Exception("No message to send to user. This should not happen.")

            return friend, message

        return None, None

    LIKE_STATUS_XPATHS = [
        "//a[text()='Like']"
    ]

    def engage_with_statuses(self, cli_bar: tqdm):
        """
        Casually like statuses of friends on the feed.
        This makes the bot look more human, increases engagement & will likely work in my favor.
        """
        self.driver.get('https://mbasic.facebook.com')

        # Get the feed
        homepage_like_buttons = []
        try:
            for xpath in self.LIKE_STATUS_XPATHS:
                homepage_like_buttons = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located((By.XPATH, xpath)))
                if len(homepage_like_buttons) > 0:
                    break

        except:
            # Unable to find any status on main page, moving to "see more stories"
            try:
                see_more_stories_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//a[text()='See More Stories']"))
                )
                self.scroll_into_view(see_more_stories_button, center=True)
                time.sleep(1)
                see_more_stories_button.click()

                self.engage_with_statuses()  # Retry
            except:
                pass

        random.shuffle(homepage_like_buttons[1:])

        for like_button in homepage_like_buttons:
            parent_attribute = like_button.find_element(By.XPATH, "//parent::span")
            status_id = parent_attribute.get_attribute('id')

            if FacebookStatusEngagement.has_engaged_with(status_id):
                self.debug(f"Skipping status {status_id} - already engaged with.")
                continue

            if random.randint(0, 100) > self.config['engagement']['like_status_chance']:
                continue

            self.scroll_into_view(like_button, center=True)
            time.sleep(1)

            like_button.click()
            FacebookStatusEngagement(post_id=status_id).save(commit=True)
            break

    def sleep_after_error(self):
        sleep_time = random.randint(self.config['sleep_min'], self.config['sleep_max'])
        self.debug(f"@@ Sleeping for {sleep_time}s after finding error page.")
        ActionLog.log("timestamp_errorpage_sleep_finish", datetime.datetime.utcnow().timestamp() + sleep_time)
        ActionLog.log('errorpage_sleep_amount', sleep_time)
        self.sleeping_after_error_page = True

    def execute_message(self, friend: FacebookUser, message: str, progress_bar: tqdm = None) -> bool:
        """
        Send the message to the user. If they're ignored (not able to message) then we'll immediately return false.
        """
        if friend.ignore is True:
            self.debug(f"~ Ignoring {friend.name} - they're on the ignore list.", progress_bar=progress_bar)
            return False

        try:
            self.driver.get(friend.url)
        except:
            self.debug(f"~ Error navigating to {friend.name} profile page (timeout 30s)", progress_bar=progress_bar)
            return False

        try:
            profile_header_buttons = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//a[text()='Message']")))
            message_buttons = profile_header_buttons[0]
            self.scroll_into_view(message_buttons)
            message_buttons.click()

            if self.has_error_page():
                self.debug(f"~ Error page when navigating to {friend.name} message page.", progress_bar=progress_bar)
                self.sleep_after_error()
                return False
        except:
            friend.ignore = True
            friend.save(commit=True)
            self.debug(f"~ Unable to message {friend.name} - they're not accepting messages. Added to ignore",
                       progress_bar=progress_bar)
            return False

        # Check for duplicate messages on the page itself. Could have happened!

        found_message_history = False

        message_history = []

        self.debug(f"~ Looking for message history on {friend.name}", progress_bar=progress_bar)

        # Looking for message history
        for element_xpath in self.MESSAGE_HISTORY_XPATHS:
            try:
                message_history = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_all_elements_located((By.XPATH, element_xpath))
                )
                found_message_history = True
            except:
                pass

        if found_message_history:

            message_links = utils.extract_urls(message)

            for message_element in message_history:
                previous_message_text = message_element.text.replace('/-', '/')

                if utils.message_contains_any_links(previous_message_text, message_links):
                    self.debug(f"~ Message to {friend.name} contains links already sent. Skipping.")
                    message_model = FacebookMessage(user=friend, message=previous_message_text)
                    message_model.save(commit=True)
                    return False
                similarity_in_messages = jellyfish.jaro_winkler_similarity(previous_message_text, message)
                if similarity_in_messages >= self.config["messaging"][
                    "similarity_limit"]:
                    self.debug(
                        f"~ Similarity in message history: {similarity_in_messages}\n\t{previous_message_text}\n\t{message}")
                    message_model = FacebookMessage(user=friend, message=previous_message_text)
                    message_model.save(commit=True)
                    return False

        self.debug(f"~ Sending message to {friend.name}", progress_bar=progress_bar)
        try:
            message_box = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//textarea[@id="composerInput"]')))
            self.scroll_into_view(message_box)
            message_box.send_keys(message)
        except:
            try:
                message_box = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, '//textarea')))
                self.scroll_into_view(message_box)
                message_box.send_keys(message)
            except Exception as ex:
                traceback.print_exc()
                self.debug(f"~ Unable to message {friend.name} - Skipping", progress_bar=progress_bar)
                friend.ignore = True
                friend.save(commit=True)
                return False

        try:
            send_button = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//input[@value="Send"]')))
            self.scroll_into_view(send_button)
            try:
                if self.config['debug']['testing-input']:
                    input("Press enter to send message")

                send_button.click()
            except:
                self.debug(f"~ Error sending message to {friend.name} - Skipping", progress_bar=progress_bar)
                return False
            if self.has_error_page():
                self.debug(f"~ Sleeping after error page when sending message to {friend.name}",
                           progress_bar=progress_bar)
                self.sleep_after_error()
                return

            message = FacebookMessage(user=friend, message=message, timestamp=datetime.datetime.now())
            message.save(commit=True)
        except:
            return False

        return True

    def begin_messaging_friends_in_sequence(self, send_friend_requests_while_sleeping=False):
        """
        Send messages to people on the friends list.

        Will employ duplicate message detection & link detection to avoid spamming.
        Spintax comments supported to generate messages.
        """

        friends: List[FacebookUser] = FacebookUser.query.filter_by(ignore=False).all()
        random.shuffle(friends)

        friends_to_message = []
        friends_progress_bar = tqdm(friends)
        for friend in friends_progress_bar:
            try:
                _message = utils.generate_comment_using_spintax(text=random.choice(self.config['comments']),
                                                                tags_to_query=self.config['descriptive_tags'],
                                                                author_name=friend.name.split(" ")[0])
            except Exception as e:
                msg = traceback.format_exc()
                self.debug(msg)
                self.debug(f"Failed to generate message for {friend.name}.")
                continue

            if friend.has_sent_similar_message(message=_message,
                                               similarity_max=self.config['messaging']['similarity_limit'],
                                               ignore_duplicate_links=False) or friend.ignore is True:
                continue

            friends_progress_bar.set_description(f"~ Will message {friend.name}.")

            if not self.execute_message(friend, _message):
                self.debug(f"Unable to message {friend.name} - Skipping.")
                continue

            sleep_time = self.get_random_sleep_time()

            if not send_friend_requests_while_sleeping:
                self.debug(f"~ Sent message to {friend.name} - Sleeping for {sleep_time} seconds",
                           progress_bar=friends_progress_bar)

                time.sleep(sleep_time)
                continue

            else:
                self.sleeping_after_message = True
                sleep_time = random.randint(self.config['messaging']['sleep_min'],
                                            self.config['messaging']['sleep_max'])
                self.timestamp_message_sleep_finish = datetime.datetime.utcnow().timestamp() + sleep_time
                ActionLog.log('timestamp_message_sleep_finish', self.timestamp_message_sleep_finish)
                self.debug(f"~ Sleeping messages for {sleep_time} seconds. Moving to another operation.")
                break

    def index_friends_list_for_database(self):
        """
        Update the database with the friends list. This will be used to send messages to.
        """
        self.driver.get(FacebookLinks.MY_FRIENDS.value)
        self.debug("Indexing friends list...")

        # Find the friends elements & compile them.

        current_friends = FacebookUser.query.filter_by(ignore=False).all()
        all_current_friends_accounted_for = {}

        for user in current_friends:
            all_current_friends_accounted_for[user.name] = False

        while True:
            try:
                friend_elements = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, '//*[@class="x u"]//a'))
                )
            except:
                break

            friend_progress_bar = tqdm(friend_elements)
            for friend_element in friend_progress_bar:
                try:
                    friend_profile_url = friend_element.get_attribute('href')
                    friend = FacebookUser.query.filter_by(name=friend_element.text).first()

                    all_current_friends_accounted_for[friend_element.text] = True

                    if friend is None:
                        try:
                            friend = FacebookUser(url=friend_profile_url, name=friend_element.text)
                            friend.save(commit=True)
                            friend_progress_bar.set_description(f"~ Added {friend.name} to database.")
                        except Exception as ex:
                            traceback.print_exc()
                            friend_progress_bar.set_description(f"~ {friend.name} already in database.")
                            continue
                    friend_progress_bar.set_description(f"~ {friend.name} already in database.")
                except Exception as e:
                    continue

            # Click that "See more" button"
            try:
                see_more_friends_button = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//div[@id="m_more_friends"]//a')
                    )
                )
                self.scroll_into_view(see_more_friends_button)
                see_more_friends_button.click()
            except:
                self.debug("~ No more friends to index for database - Moving onto next operation.")
                break

        # Remove friends that are no longer on the friends list.
        for friend_name, accounted_for in all_current_friends_accounted_for.items():
            if not accounted_for:
                friend = FacebookUser.query.filter_by(name=friend_name).first()
                if friend is not None:
                    friend.ignore = True
                    friend.save(commit=True)
                    self.debug(f"~ Removed {friend.name} added to ignore in database.")

    def add_users(self, add_with_most_mutual=True, message_while_sleeping=False):
        """
        Send friend requests on FaceBook, pausing to not hit to much of a rate limit.
        """

        # Find the friends elements

        sent_requests = 0

        friend_requests_progress_bar = tqdm([i for i in range(0, self.config['friend_requests']['request_limit'])])
        self.debug(f"~ Starting to add users.", progress_bar=friend_requests_progress_bar)

        for i in friend_requests_progress_bar:
            try:
                self.driver.get(FacebookLinks.ADD_FRIENDS.value)
            except:
                self.debug("~ Unable to load page.")
                break
            try:
                friend_elements = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, '//div[@class="x cd"]/table/tbody/tr/td[2]'))
                )

            except:
                self.debug("~ Nobody to add!", progress_bar=friend_requests_progress_bar)
                return None

            selected_friend_element = None

            if friend_elements is None:
                self.debug("~ Unable to locate any elements on the page via xpath.")
                continue

            random.shuffle(friend_elements)
            selected_friend_element = random.choice(friend_elements)
            if selected_friend_element is None:
                continue

            try:
                friend_name = selected_friend_element.find_element(By.XPATH, '//a[@class="cg"]').text.strip()
                self.debug(f"~ Selected {friend_name} to add", progress_bar=friend_requests_progress_bar)
            except:
                continue

            # Click the element & send friend request
            try:
                friend_name = selected_friend_element.find_element(By.XPATH, '//a[@class="cg"]').text.strip()
                add_friend_link = selected_friend_element.find_element(By.XPATH,
                                                                       '//a[@class="ba bc cn co be bb"]')

                self.scroll_into_view(add_friend_link)
                time.sleep(1)
                add_friend_link.click()

                if self.has_error_page():
                    self.sleep_after_error()
                    return
            except:
                traceback.print_exc()
                self.debug("~ Couldn't add friend! Skipping...", progress_bar=friend_requests_progress_bar)
                continue

            if not message_while_sleeping:
                sent_requests += 1
                sleep_time = self.get_random_sleep_time()
                self.debug(f"~ Added {friend_name} - Sleeping for {sleep_time} seconds",
                           progress_bar=friend_requests_progress_bar)
                time.sleep(sleep_time)
                continue

            self.debug(f"~ Added {friend_name} - Moving to messages", progress_bar=friend_requests_progress_bar)
            break

    def begin(self):
        """
        Initiate the bot & begin the operations.

        Depending on the mode of operation (smart sleeping / sequential)
        it will perform a different logic loop.
        """
        if not self.setup_complete:
            self.startup(config_file_name=self.config_file_name)

        if not ActionLog.updated_within_range("facebook_friends_indexing", hours_ago=5) or self.config['friend_requests']['force_indexing'] or self.force_friend_indexing:
            self.debug("~ Indexing friends list... Been more than 5 hours since last indexing.")
            self.index_friends_list_for_database()
            ActionLog.log("facebook_friends_indexing", datetime.datetime.utcnow())

        if not self.config['smart_sleep']:

            if self.config['friend_requests']['enabled']:
                self.debug("~ Sending friend requests...")
                self.add_users()

            if self.config['messages']['enabled']:
                self.debug("~ Sending messages...")
                self.begin_messaging_friends_in_sequence()

            return

        else:
            self.debug("~ Smart sleep enabled. Sending messages & friend requests while sleeping")
            self.perform_smart_sleep_loop()
