import abc
import datetime
import platform
import pprint
import random
import sys
import time

import logging
import traceback

from slapbot.logging import setup_logging

import seleniumwire.undetected_chromedriver as uc
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

import os

from abc import ABC
from slapbot import utils
from slapbot.extensions import db

# fix this shit
selenium_logger = logging.getLogger('seleniumwire')
selenium_logger.setLevel(logging.ERROR)


def windows_enable_ansi_terminal():
    if (sys.platform != "win32"):
        return None
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        result = kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        if (result == 0): raise Exception
        return True
    except:
        return False


class DriverType:
    FIREFOX = "geckodriver"
    CHROME = "chromedriver"
    UNDETECTED_CHROME = "uc"


class Interaction:
    COMMENT = "comment"
    LIKE = "like"
    PLAY = "play"
    REPOST = "repost"

    @staticmethod
    def get(text):
        if text.lower() == "comment":
            return Interaction.COMMENT

        if text.lower() == "like":
            return Interaction.LIKE

        if text.lower() == "play":
            return Interaction.PLAY

        if text.lower() == "repost":
            return Interaction.REPOST

        return None


class BotBase(ABC):
    """
    Abstract base class for all bots
    """

    def __init__(self):
        self.println = None
        self.bot_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]

        self.debug_silence = False

        self._config = dict()

        self.progress_bar = None

    def _setup_logging(self):
        if windows_enable_ansi_terminal():
            print(f"Enabled windows console colors")

        pass

    def debug(self, text: str, msg_type="info", progress_bar: tqdm = None, fg="white", bg="black", bold=False,
              underline=False, blink=False, reverse=False, println=False):
        _println = self.println is True or println is True
        utils.debug(text, msg_type, progress_bar if progress_bar is not None else self.progress_bar, fg, bg, bold,
                    underline, blink, reverse, println=_println)

    def begin(self):
        self.startup()

    @abc.abstractmethod
    def startup(self):
        pass


class RequestsBot(BotBase):
    """
    Base for a multi-threaded requests bot (usually used for scraping data)
    """

    def __init__(self):
        super(RequestsBot, self).__init__()


class BrowserBotBase(BotBase):
    """
    Base class used in abstraction to aid the design of automation projects.

    This base handles the following (for abstractions):
        - Log saving
        - Debugging
        - helper methods.
        - automatic browser creation based on browser
        - special syntax parsing for comment generation based on random elements, and human logic.
        -
    """

    def __init__(self, driver_type: DriverType = DriverType.FIREFOX, headless=False, late_init=False,
                 proxy_list_file=None):
        """
        :param driver_type: The type of driver to use.
        :param headless: If the browser should be headless.
        :param late_init: If the browser should be initialized later, and not when the class is created.
        :param proxy_list_file: The file to load proxies from (if any). Completely optional.
        """
        super(BrowserBotBase, self).__init__()
        self.last_config_load_timestamp = None
        self.config_reload_time = 20
        self.config_file_name = ""
        self.setup_complete = False
        self.profile = None
        self.driver_type = driver_type
        self._driver = None
        self.late_init = late_init
        self.headless = headless

        self.attempt_to_center_scroll = True

        self.profile_location = None
        if self.driver_type == DriverType.FIREFOX:
            self.profile_location = self.locate_firefox_profile()
        else:
            self.profile_location = self.locate_chrome_profile()

        self.comment_log = []

        self._setup_logging()

        if not late_init:
            self.init_driver()

    def init_driver(self, use_profile=True, profile_location=None):
        """
        Initialize the bot driver. This is called automatically if late_init is False.
        :param use_profile: If the driver should use a profile.
        :param profile_location: The location of the profile to use if using one.
        """

        self.debug(f"Selected Driver: {self.driver_type}")

        if self.driver_type == DriverType.FIREFOX:
            options = FirefoxOptions()
            options.headless = self.headless
            options.binary_location = r'C:\Program Files\Mozilla Firefox\firefox.exe'
            #
            executable_path = None
            if platform.system() == "Windows":
                executable_path = "geckodriver.exe"
            else:
                executable_path = "geckodriver"

            executable_path = os.path.join(os.getcwd(), executable_path)
            self.debug(f"Executable Path: {executable_path}")

            service = FirefoxService(executable_path=executable_path)

            if use_profile:
                profile = profile_location if profile_location is not None else self.locate_firefox_profile()
                self.debug(f"Using profile: {profile}")
                options.set_preference('profile',
                                       profile_location if profile_location is not None else self.locate_firefox_profile())

                options.add_argument('-profile')
                options.add_argument(profile)

            self._driver = webdriver.Firefox(service=service, options=options)

        else:
            if self.driver_type == DriverType.UNDETECTED_CHROME:
                self.profile = uc.ChromeOptions()
            else:
                self.profile = webdriver.ChromeOptions()
            # self.profile = webdriver.ChromeOptions()
            if use_profile:
                #
                try:
                    self.profile.user_data_dir = profile_location if profile_location is not None else self.locate_chrome_profile()
                    print(f"Using profile: {self.profile.user_data_dir}")
                    print(f"{pprint.pformat(self.profile.__dict__, indent=2)}")
                except:
                    print(
                        f"Unable to set profile location on undetected chromedriver, trying to set it on normal chromedriver.")
                    self.profile.add_argument("user-data-dir={0}".format(
                        profile_location if profile_location is not None else self.locate_chrome_profile()))

                    pass

            self.profile.headless = self.headless

            if self.driver_type == DriverType.UNDETECTED_CHROME:
                self._driver = uc.Chrome(
                    chrome_options=self.profile
                )
            else:
                self._driver = webdriver.Chrome(
                    options=self.profile
                )

    @property
    def driver(self):
        if self._driver is None:
            self.init_driver()
            try:
                self._driver.minimize_window()
            except:
                pass
        return self._driver

    def scroll_into_view(self, element, center=False):
        """
        Executes javascript to scroll element into view.
        Optionally center the element in the middle of the page.
        """

        try:
            if center or self.attempt_to_center_scroll:
                desired_y = (element.size['height'] / 2) + element.location['y']
                window_h = self.driver.execute_script('return window.innerHeight')
                window_y = self.driver.execute_script('return window.pageYOffset')
                current_y = (window_h / 2) + window_y
                scroll_y_by = desired_y - current_y

                self.driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_y_by)
            else:
                self.driver.execute_script('arguments[0].scrollIntoView();', element)
        except Exception as e:
            raise e

    def scroll_with_javascript(self, pixel_amount: int):
        self.driver.execute_script(f"window.scrollBy(0,{pixel_amount});")

    def set_text_via_javascript(self, element, text):
        """
        Set the text of an element via javascript.
        """

        js_code = """
          var elm = arguments[0], txt = arguments[1];
          elm.value += txt;
          elm.dispatchEvent(new Event('change'));
        """

        self.driver.execute_script(js_code, element, text)

    def send_keypress_to_page(self, key=Keys.END, count=1, sleep_time=1, element=None):
        """
        Scroll down the page by sending keys to the html element
        """
        try:
            element = self.driver.find_element(By.TAG_NAME, "html") if element is None else element

            for i in range(1, count):
                element.send_keys(key)
                time.sleep(sleep_time)
                self.driver.implicitly_wait(sleep_time)

        except Exception as e:
            traceback.print_exc()
            self.debug("Error when scrolling with keypress")
            time.sleep(5)

    def scroll_up_with_key_press(self, key=Keys.PAGE_UP, count=2, sleep_time=1):
        """
        Scroll up the page with page up.
        """
        self.send_keypress_to_page(key=key, count=count, sleep_time=sleep_time)

    def locate_chrome_profile(self):
        """
        Locates the default chrome profile for use on the bot.
        """
        chrome_profile_location = os.path.expanduser(
            "~/AppData/Local/Google/Chrome/User Data/".replace("/", os.sep)
        )

        if not os.path.exists(chrome_profile_location):
            self.debug(
                "Unable to locate parent folder for the Chrome user profiles. Please launch chrome, login to the web app, and retry this application again")
            return None

        default_chrome_profile_location = os.path.expanduser(
            "~\\AppData\\Local\\Google\\Chrome\\User Data\\Default"
        )

        if not os.path.exists(default_chrome_profile_location):
            self.debug("Unable to locate default chrome profile")
            return None

        return chrome_profile_location

    def locate_firefox_profile(self):
        """
        Locates the default firefox profile
        """

        firefox_profiles_location = None

        if 'posix' in os.name:
            firefox_profiles_location = os.path.expanduser(
                "~/Library/Application Support/Firefox/Profiles/"
            )
        elif 'nt' in os.name:
            firefox_profiles_location = os.path.expanduser(
                "~\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\"
            )
        else:
            firefox_profiles_location = os.path.expanduser(
                "~/AppData/Roaming/Mozilla/Firefox/Profiles/"
            )

        if not os.path.exists(firefox_profiles_location):
            self.debug(
                "Unable to locate parent folder for Firefox user profiles. Please launch firefox, login to the web app, and retry this application again.")
            return None

        subfolders = [f.path for f in os.scandir(firefox_profiles_location) if f.is_dir()]

        for folder in subfolders:
            if '.default-release' not in folder or '.default' not in folder:
                continue

            return folder

        return None

    def check_xpath_exists(self, xpath):

        try:
            self.driver.find_element(By.XPATH, xpath)
        except NoSuchElementException:
            return False

        return True

    @property
    def config(self):
        """
        Returns the config object
        """
        timestamp = datetime.datetime.utcnow().timestamp()

        if self.last_config_load_timestamp is None or timestamp - self.last_config_load_timestamp >= self.config_reload_time:
            try:
                self._config = utils.load_config(config_file_name=self.config_file_name, default_config=self._config)
            except Exception as e:
                traceback.print_exc()
                return

            self.last_config_load_timestamp = timestamp
        return self._config

    @config.setter
    def config_setter(self, value):
        self._config = value

    def startup(self, config_file_name, driver_type=None):
        if driver_type is None:
            driver_type = self.driver_type

        if not self.setup_complete:
            try:
                db.create_all()
                print("Created database tables")
            except Exception as e:
                print(e)
                return

            try:
                self.debug(f" ~ Loading config from {config_file_name}")
                self._config = utils.load_config(config_file_name=config_file_name, default_config=self._config)
            except Exception as e:
                print(e)
                return
            print(f"+ Loaded {config_file_name}")

            if self.late_init is True:
                print(
                    f"Initializing browser with profile @ {self.config['firefox_profile_path'] if driver_type is DriverType.FIREFOX else self.config['chrome_profile_path']}")
                self.init_driver(
                    profile_location=self.config['firefox_profile_path'] if driver_type is DriverType.FIREFOX else
                    self.config['chrome_profile_path'])

            self.setup_complete = True

    def wait_and_retry(self, expected_condition: EC, locator: tuple, timeout=10, retry_count=1):

        """
        Returns a boolean value if it succeeded, or failed.
        """
        success = False
        for i in range(0, retry_count):
            if success is True:
                break

            try:
                wait = WebDriverWait(self.driver, timeout=timeout).until(expected_condition(locator))
                success = True
            except Exception as exception:
                traceback.print_exc()
                self.debug(f"Failed Attempt #{i} waiting for element")

        return success
