import platform


class Config(object):
    Debug = True
    TESTING = False
    SQLALCHEMY_POOL_SIZE = 100
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300
    SPOTIFY_CLIENT_ID = ""
    SPOTIFY_CLIENT_SECRET = ""
    YOUTUBE_API_KEY= "AIzaSyA4ZepVzWEwtrRrTapHKGCCFBe9bgvpiIY"

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        if platform.system() == "Windows":
            return 'postgresql://postgres:password@localhost:5432/slapbot'
        else:
            return 'postgresql://localhost:5432/slapbot'


class TestConfig(Config):
    Debug = True
    TESTING = True

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        if platform.system() == "Windows":
            return 'postgresql://postgres:password@localhost:5432/slapbot-testing'
        else:
            return 'postgresql://localhost:5433/testing'
