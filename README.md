ABOUT
----
🤖 Niche bot with a purpose of delivering messages tailored to your fanbase.

**The Tech Specs**
* [Spintax](https://github.com/AceLewis/spintax) library backed for text generation.
* _Implementation with ChatGPT for smart messaging_
* Nuxt.js Dashboard (See [frontend](https://github.com/Islati/slapbot-web-ui)
* Massive configuration for smart looping
  * _Sleep actions & perform others rather than waiting immediately after an action, to reduce bot detection_
* Database to hold all information in "Profiles" (Includes _users socials_, _songs_, _message history_, _etc_)
  * Each profile has multiple social media accounts linked to it, allowing all data to be easily navigated & displayed.

Python Powered
* [Flask](https://flask.palletsprojects.com/en/2.3.x/) for dashboard, API, and ORM Integration
* [Typer](https://typer.tiangolo.com/typer-cli/) for the CLI scripts
* [Jellyfish](https://pypi.org/project/jellyfish/) for String comparison (Detection of duplicate messages, messages to similar... Bot detection reduction)
* [Selenium](https://selenium-python.readthedocs.io/) for data scraping websites.
  * Requries profiles to be configured in appropriate bots `*_config.json` file
* [Pytest](https://docs.pytest.org/en/7.3.x/) Testing framework

```
## **Initial Concept:**

- Search youtube for recent uploads and comment on them
- comments are generated using spintax
- logic implemented to not post on the same video twice
- log of all videos posted on.


**Development Requirements**

_(Initialize selenium with firefox profile already logged in to youtube)_
* Search for terms and scrape all URLS
* Compare scraped urls against previously commented items.
* Navigate to video
* Await comment box being loaded on scroll
* Post comment
* Wait like 45 - 60 seconds
* At times give the beat a like
* option to subscribe to users
* feature in the future to mass unsub
```

Setup & Usage
----

Pick a bot that you'd like to use. 

Available bots:
* YouTube
  * Commenting
  * Subscribing
* Slaps
  * Commenting
  * Direct Messaging
* FaceBook
  * Messaging
  * Friend Adding
  * Status Interaction
* Reddit
  * Account Messenger


## Initial Setup

1. Install Python 3.11+ to a virtual environment & execute `pip install -r requirements.txt`

2. Install & Have ready a Postgres 14+ Database Server
1. Create a `slapbot` database using pgAdmin4 or some other way.
2. Configure `slapbot/config.py` with your database credentials
   * ```python
       class Config(object):
           Debug = True
           TESTING = False
           SQLALCHEMY_POOL_SIZE = 100
           CACHE_TYPE = "SimpleCache"
           CACHE_DEFAULT_TIMEOUT = 300
           SPOTIFY_CLIENT_ID = ""
           SPOTIFY_CLIENT_SECRET = ""
    
           @property
           def SQLALCHEMY_DATABASE_URI(self):
               if platform.system() == "Windows":
                   return 'postgresql://postgres:password@localhost:5432/slapbot'
               else:
                   return 'postgresql://localhost:5432/slapbot'
       ```

3. Navigate to the `slapbot` directory & run migrations to setup the database: `flask db upgrade`
   * Flask is used here to support the [frontend-ui](https://github.com/Islati/slapbot-web-ui)
4. Install FireFox for the bots
   * Also supports Chrome, and UndetectedChromeDriver but I've found FireFox to be the most stable, and fastest.
5. Return to directory where `cli.py` exists
6. Run the following command to view the bots available commands: `python cli.py --help`

_ChatGPT Message generation (via prompt) is not fully tested and therefore not documented._
  * I do however suggest teaching spintax to your ChatGPT session & generating messages to use 👀 [(example)](https://gist.github.com/Islati/384beb0f1878067d712996e7944c5c0d)

### 🤖 Configuring Youtube Bot Runner

When you run (_for example_) the `python cli.py youtube`  command you'll have a bot launch, and that bot will auto create a selenium instance & begin its actions.
It's recommended to kill the script the first instance, log in, and configure your `youtube_config.json` file.

It will look something like:

```python
self._config = dict(
    wait_times = dict(  # how long to wait between posting another comment on videos
        comment_wait_hours=12,
        comment_wait_days=4
    ),
    subscribe = dict(  # optional chances to subscribe to the channel it's commenting on
        enabled=True,
        chance=100
    ),
    like = {  # optional chances to like the video it's commenting on
        'enabled': True,
        'chance': 100
    },
    search_option = "EgIIAQ%253D%253D",  # Search option for youtube
    wait_time_min = 20,  # min wait time between actions
    wait_time_max = 25,  # max wait time between actions
    video_search_limit = 50,  # how many video to scrape per search
    firefox_profile_path = ""  # Path to your firefox profile (auto located if available)
    restart_when_finished = True,  #
    title_restriction = True,  # Enforce (enable) title_filter on videos
    title_filter = "type beat",  # Only comment on videos with this in the title
    restart_cooldown_time = 4800,  # Wait an hour and a half,
    restart_cooldown_time_min = 100,  # wait time after it's finished everything (min)
    restart_cooldown_time_max = 200,  # wait time after it's finished everything (max)
    scroll_pixels = 700,  # how far down the page the comment section is
    wait_days_between_channel_comment = 3,  # how long to wait before commenting on another video this channel uploads
    maximum_waits = 5,
    queries = [
        "biggie smalls type beat",
        "fresh type beat",
        "chill type beat",
        "old school type beat",
        "freestyle"
    ],
    
    comments = [
        "[compliment] {[smiley-face]|}"
    ],
    # There are [tags] that can be used to select & generate random text elements
    descriptive_tags = {
        "smiley-face": [
            "🔥"
        ],
        "compliment": [
            "[smiley-face] {Tap in with me|Tap in|Lets cook|You open to collab?|HMU for a collab|||}",
         ],
    } #end of descriptive tags
)
```

### 🤖 Configuring Slaps Bot

When you run `python cli.py slapbot --driver FireFox` you'll have a `slapbot_config.json` file generated for you by default.


Values are going to be as follows, but in json format _(pulled from `slaps.py`)_

```python
self._config = dict(
            debug=True, # debug mode (enables checks before posting)
            username="Islati", #Your slaps.com username (used to avoid some interesting behaviour)
            slaps_search_url="https://slaps.com/?action=&id=&sort=",
            firefox_profile_path="", #auto located by default if possible
            chrome_profile_path="", # auto located by default if possible
            wait_time_min=45,
            wait_time_max=90,
            scroll_min=10,
            scroll_max=100,
            captcha_wait_time=30,
            requires_login=True, # requires login (if false, will skip login)
            user_scraping=dict( # user scraping
                followers_and_following=False, # scrape followers and following
                hot_tab=False, # scrape hot tab
                new_tab=True, # scrape new tab
                enabled=True, # enable user scraping
                hours_to_wait=2, # hours to wait before scraping again
                deep_scrape_days=7, # days to scrape for deep scraping
                messaging_enabled=True, # enable messaging
                messaging_sleep_min=60, # min sleep time for messaging
                messaging_sleep_max=300, # max sleep time for messaging
            ),
            exits=dict(
                post_inboxing=False, # inbox posts
                post_unfollowed_leads_messages=False # inbox unfollowed leads
            ),
            messaging=dict(
                check_recently_active=True, # check if user has been recently active
                update_message_history=True, # update message history (saving them to database)
                check_for_duplicates=True, # check for duplicate messages
                only_message_if_not_following=True, # only message if not following
                similarity_limit=0.75, # 75% similarity limit in messages allowed (see jellyfish library)
                valid_inbox_thread_kill_switch_count=50, # kill switch for inboxing [legacy]
                inbox_existing_conversations=False, # inbox existing conversations
                inboxing_reverse_order=False, # inbox in reverse order (oldest first) [legacy mode]
                unfollowed_leads_batches=1, # 1 batch per run [legacy]
                unfollowed_leads_batch_limit=500, # 500 leads per batch [legacy]
                ignore_duplicate_links=False, # ignore duplicate links in messages (avoiding spam)
                wait_times=dict( # wait times between messaging the same user again
                    wait_skip=False, # skip wait times
                    days_to_wait=10, # wait 10 days 
                    hours_to_wait=14, # wait 14 hours
                ),
            ),
            message_unfollowed_leads=dict( # message unfollowed leads settings (great for new followers)
                enabled=True, # enable unfollowed leads messaging
                sleep_min=90, # sleep for 90 seconds (1.5 minutes)
                sleep_max=3600, # sleep for 3600 seconds (1 hour)
            ),
            error_failsafe=dict( # error failsafe settings (happens after somethings breaks)
                sleep_min=1600, # sleep for 1600 seconds (26 minutes)
                sleep_max=3600 # sleep for 3600 seconds (1 hour) 
            ),
            comment_settings=dict( # more comment settings
                use_chat_gpt=False, # use chat gpt to generate comments (no longer supported)
                use_openai=False, # use openai to generate comments
                open_ai_secret_key="",
                chat_gpt_session_token="", # no longer required, will be deprecated
            ),
            direct_messages=[ #direct messages are used to message other users
                "Hey, what's up [author] Check out [songplug]"
            ],
            comments=[ #comments are used to comment on songs
                "Hey, what's up [author] Check out [songplug]"
            ],
            descriptive_tags={ #descriptive tags are used to generate random messages
                "songplug": [
                    "my new rap song `Free Game` available at http://free-game.skreet.ca to listen on all platforms & ask them put it on a playlist and to keep in touch",
                ]
            },
            ai_prompts={ #ai prompts are used to generate random messages
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

            song_liking=dict( #liking songs
                enabled=True, #whether or not to enable this feature
                like_chance=100, #chance to like a song
                love_chance=5, #chance to love a song
                sleep_min=5, #minimum time to sleep after liking
                sleep_max=30, #maximum time to sleep after liking
            ),
            song_commenting=dict( #commenting on songs
                enabled=True, #whether or not to enable this feature
                comment_chance=100, #chance to comment on a song
                sleep_min=5, #minimum time to sleep after commenting
                sleep_max=80, #maximum time to sleep after commenting
                sort_by="new", #how to sort the songs (new, hot)
                scroll_min=1, #minimum amount of times to scroll down the page
                scroll_max=15, #maximum amount of times to scroll down the page
                max_comment_search_iterations=10, #maximum amount of times to search for a song to comment on
                sleep_after_comment=True #whether or not to sleep after commenting
            ),
            smart_loop=dict( #smart loop is a feature that will automatically loop through all actions & only sleep when necessary
                enabled=True, #recommended to enable
                page_refresh_time=60 * 30 #time to wait before refreshing the page
            ),
            headless=False, #whether or not to run the browser in headless mode
            finish_restart_wait_time_min=4500, #minimum time to wait before restarting the browser
            finish_restart_wait_time_max=6000, #maximum time to wait before restarting the browser
            config_reload_time=20, #time to wait before reloading the config file
        )
```

### Configuring Facebook Bot

Facebook Bot runs through `mbasic.facebook.com` which has some limitations. It's recommended to have long wait times, not include links in messages, and only use this sparingly. 



```python
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
```

### Configuring Other Bots

* Soundcloud Bot
  * Currently, Out of Date & Not Working. Bot protection is strong.
* Hackforums Bot
  * Bot protection is strong.
* Tiktok Bot
  * Programtically functional but it doesn't reflect on the app. Bot protection is strong.
* Reddit Bot
  * Bot protection is strong. Community is against it. 
* Audiomack Bot
  * Has not been tested in a very long time.

### Final Notes
_This bot is not in active development, and was built so I could source the ultimate playlist of underground upcoming artists (originally)_
