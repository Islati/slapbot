import random
import time
import urllib.parse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from slapbot.bots import BrowserBotBase, DriverType

"""
    OFFICIALLY RETIRED @ APRIL 23 2021
    
    Open April 25'th:
        - Reddit accounts require KARMA to avoid recaptcha when sending messages. Possible it also requires a time
"""


class RedditBot(BrowserBotBase):

    def __init__(self):
        super().__init__(driver_type=DriverType.CHROME)

        # Collection of usernames from reddit searces
        self.search_scraped_usernames = []
        self.skip_urls = []
        self.collected_users = []

        self.config = {
            'wait_time_min': 90,
            'wait_time_max': 500,
            'perform_search_and_scrape': True,
            'limit_scraped_threads': 2,
            "user_blacklist": [
                "automoderator",
            ],
            'search_urls': [
                {
                    'description': 'Daily thread of users promoting their music. Prime for collecting submissions to playlists.',
                    'url': 'https://www.reddit.com/r/makinghiphop/search/?q=%5BOFFICIAL%5D+DAILY+FEEDBACK+THREAD&sort=new&restrict_sr=on&t=all',
                }
            ],
            'urls': [
                'https://www.reddit.com/r/makinghiphop/comments/mho0kz/official_daily_feedback_thread/'
            ],
            "titles": [
                "{Free|} {feature|promo|spotify playlist|playlist|music opportunity|hip hop playlist}"
            ],
            "comments": [
                "{[greeting]|} [final_words] {[smiley-face]| }",
            ],
            "descriptive_tags": {
                "final_words": [
                    "Bless {up|}",
                    "Cheers{!|}",
                    "Stay {blessed|motivated|focused|true}{!|.}",
                    "Much love{!|.}"
                ],
                "smiley-face": [
                    ":)",
                    ":]",
                ],
            },

        }

    def startup(self):
        if not self.setup_complete:
            self.load_config(config_file_name="reddit_bot_config.json")
            print("Loaded reddit_bot_config.json")

            if len(self.config['urls']) < 1 and self.config['perform_search_and_scrape'] is False:
                print(
                    "Please configure the bot with urls to collect users from, or search urls to find threads to find users in.")
                exit(-9)
                return

            self.comment_log = self.load_json_file("reddit_bot_log.json")
            print(f"Loaded {len(self.comment_log)} previous messages")
            self.setup_complete = True
            print("Setup complete")

    def begin(self):
        if not self.setup_complete:
            self.startup()
            time.sleep(2)

        print("Beginning to collect recent threads")
        has_search_urls = len(self.config['search_urls']) > 0
        collected_threads = []
        if has_search_urls:
            print(" -- Performing searches")
            threads = self.search_urls_and_scrape()
            for thread in threads:
                collected_threads.append(thread)

        has_subreddit_urls = len(self.config['subreddit_urls']) > 0
        if has_subreddit_urls:
            print(" -- Performing subreddit searches")
            threads = self.search_subreddits_and_scrape()
            for thread in threads:
                collected_threads.append(thread)

        if len(collected_threads) > 0:
            self.collect_usernames_from_threads(collected_urls=collected_threads)

            print("Search complete, beginning message sequence")
            self.message_users()
        else:
            print("No threads found on search")

    def push_log(self, user, subject, message):
        timestamp = time.time()
        self.comment_log.append({
            'user': user,
            'message': message,
            'subject': subject,
            'timestamp': timestamp
        })

    def _has_collected_user_data(self, username):
        for data in self.collected_users:
            if data['username'] == username:
                return True

        return False

    def search_subreddits_and_scrape(self):
        """
        Navigate through configured subreddits and collect users.
        """

        search_list = tqdm(self.config['subreddit_urls'])

        comments_button_xpath = "//a[contains(@class,'comments') and not(contains(@class,'empty'))]"

        thread_limit = self.config['limit_scraped_threads']
        has_limit = thread_limit > 0

        collected_urls = []
        for subreddit in search_list:
            thread_depth = 0
            self.driver.get(subreddit)

            try:
                comment_links = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_all_elements_located((By.XPATH, comments_button_xpath))
                )
            except:
                print(f"Unable to collect any threads on subreddit '{subreddit}'")
                continue

            for thread_comments_link in comment_links:
                if has_limit and thread_depth >= thread_limit:
                    break

                link = thread_comments_link.get_attribute('href')
                collected_urls.append(link)
                thread_depth += 1

        return collected_urls

    def search_urls_and_scrape(self):
        """
        Navigate through the configured search urls and collect data
        """

        search_list = tqdm(self.config['search_urls'])

        # search-comments instead of search-title just incase there's attached media.
        search_title_a_xpath = "//a[contains(@class,'search-comments')]"

        collected_urls = []

        for search in search_list:
            self.driver.get(search['url'])

            try:
                search_titles = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, search_title_a_xpath))
                )
            except:
                print("Unable to locate any searched threads.")
                continue

            thread_limit = self.config['limit_scraped_threads']
            has_limit = thread_limit > 0
            collected = 0
            for title_element in search_titles:
                link = title_element.get_attribute('href')

                if has_limit and collected >= thread_limit:
                    break
                collected_urls.append(link)
                collected += 1

        return collected_urls

    def collect_usernames_from_threads(self, collected_urls):
        """
        Navigate to reddit threads and gather usernames for messaging.
        """
        print(f"Collected {len(collected_urls)} urls to scrape usernames from")

        url_bar = tqdm(collected_urls)

        # user url tagline xpath
        thread_user_xpath = "//div[contains(@class,'entry')]/p[contains(@class,'tagline')]/a[contains(@class,'author')]"

        for url in url_bar:
            url_bar.set_description(f"{url}")

            self.driver.get(url)

            url_bar.set_description('Collecting usernames')

            # Expand all the comments on the page.
            try:
                show_more_comments_button = WebDriverWait(self.driver, timeout=10).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//a[contains(@class,'showreplies')]")
                    ))

                for show_more_button in show_more_comments_button:
                    self.scroll_into_view(show_more_button)
                    show_more_button.click()
                    time.sleep(0.5)

            except Exception as ex:
                print("Opening replies caused exception- Salvaging data by collecting users.")
                pass

            try:
                user_link_elements = WebDriverWait(self.driver, timeout=10).until(EC.presence_of_all_elements_located(
                    (By.XPATH, thread_user_xpath)
                ))
            except Exception as ex:
                url_bar.set_description("Unable to detect any comments. Skipping")
                time.sleep(1)
                continue

            users_appended = 0
            for user_link_ele in user_link_elements:
                user_link = user_link_ele.get_attribute('href')
                user_name = user_link_ele.text

                if not self._has_collected_user_data(user_name) and 'automod' not in user_link.lower():
                    self.collected_users.append(dict(
                        url=user_link,
                        username=user_name
                    ))
                    users_appended += 1
                    url_bar.set_description(f'+ {user_name}')

            print(f"+ {users_appended} users collected from {url}")

    def can_message_user(self, username):
        for log in self.comment_log:
            if log['user'] == username or log['user'] in username.lower():
                return False

        return True

    def message_users(self):

        cli_bar = tqdm(self.collected_users)

        for user in cli_bar:
            username = user['username']

            # Skip names on the blacklist
            if not self.can_message_user(username) or username in self.config['user_blacklist']:
                cli_bar.set_description(f"Skipping {username}")
                continue

            link = user['url']

            if username is None or len(username) == 0:
                continue

            title_syntax = random.choice(self.config['titles'])
            generated_subject = self.parse_text(text=title_syntax, author_name=username)
            generated_message = self.generate_comment_from_spintax(author_name=username)
            encoded_subject = urllib.parse.quote(generated_subject)
            encoded_message = urllib.parse.quote(generated_message)
            msg_user_link = f"https://www.reddit.com/message/compose/?to={username}&subject={encoded_subject}&message={encoded_message}"

            try:
                self.driver.get(msg_user_link)
            except Exception as e:
                print(e)
                exit(-9)
                return

            cli_bar.set_description(f"Messaging {username}")
            time.sleep(random.randint(2, 4))

            send_button = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//button[@id='send']")
                )
            )

            cli_bar.set_description("Preparing to click button")
            time.sleep(random.randint(1, 5))

            send_button.click()

            self.push_log(user=username, subject=generated_subject, message=generated_message)
            self.save_json_file("reddit_bot_log.json", data=self.comment_log)

            time_to_sleep = random.randint(self.config['wait_time_min'], self.config['wait_time_max'])
            cli_bar.set_description(f'Sleeping {time_to_sleep}s before next action')

            time.sleep(time_to_sleep)


if __name__ == "__main__":
    reddit_bot = RedditBot()
    while True:
        reddit_bot.begin()
        sleep_time = random.randint(reddit_bot.config['wait_time_min'], reddit_bot.config['wait_time_max']) * 2
        reddit_bot.debug(f"Sleeping for {sleep_time}s before searching again")
        time.sleep(sleep_time)
