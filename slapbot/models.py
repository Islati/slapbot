import datetime
import json
import jellyfish

from slapbot import utils
from slapbot.database import db, SqlModel, SurrogatePK, TimeMixin, foreign_key


class Location(SqlModel, SurrogatePK):
    """
    Locations, used to show where the users are.
    """

    __tablename__ = "locations"
    name = db.Column(db.Text, nullable=False, unique=True)


class Tag(SqlModel, SurrogatePK):
    """
    A tag for a track, or post of some kind.
    """
    __tablename__ = "tags"

    tag = db.Column(db.String, nullable=False, unique=True)


class UserProfile(SqlModel, SurrogatePK, TimeMixin):
    """
    Parent profile model to link all user data into one item.
    """
    __tablename__ = "user_profiles"

    slaps_user_id = foreign_key("users", nullable=True)
    slaps_user = db.relationship("SlapsUser", back_populates="profile", foreign_keys=[slaps_user_id], uselist=False,
                                 cascade="all, delete")

    youtube_channel_id = foreign_key("youtube_channels", nullable=True)
    youtube_channel = db.relationship("YoutubeChannel", back_populates="profile", foreign_keys=[youtube_channel_id],
                                      uselist=False, cascade="all, delete")

    facebook_user_id = foreign_key("facebook_users", nullable=True)
    facebook = db.relationship("FacebookUser", back_populates="profile", foreign_keys=[facebook_user_id], uselist=False,
                               cascade="all, delete")

    spotify_id = foreign_key("spotify_artists", nullable=True)
    spotify = db.relationship("SpotifyArtist", back_populates="profile", foreign_keys=[spotify_id], uselist=False,
                              cascade="all, delete")

    instagram_id = foreign_key("instagram_profiles", nullable=True)
    instagram = db.relationship("InstagramProfile", back_populates="profile", foreign_keys=[instagram_id],
                                uselist=False, cascade="all, delete")

    twitter_id = foreign_key("twitter_profiles", nullable=True)
    twitter = db.relationship("TwitterProfile", back_populates="profile", foreign_keys=[twitter_id], uselist=False,
                              cascade="all, delete")

    profile_image_url = db.Column(db.Text, nullable=True)

    # Whether or not we're watching this user.
    watching = db.Column(db.Boolean, nullable=True, default=False)

    @property
    def has_messaged(self):
        messaged_on_slaps = False

        if self.slaps_user is not None:
            return SlapsDirectMessage.query.filter(SlapsDirectMessage.user_id == self.slaps_user_id).count() > 0
        return messaged_on_slaps

    @property
    def has_received_reply(self):
        received_reply_on_slaps = False
        if self.slaps_user is not None:
            return SlapsDirectMessage.query.filter(SlapsDirectMessage.user_id == self.slaps_user_id,
                                                   SlapsDirectMessage.received == True).count() > 0
        return received_reply_on_slaps

    @property
    def has_commented(self):
        commented_on_slaps = False
        commented_on_youtube = False

        if self.slaps_user is not None:
            commented_on_slaps = SlapsComment.query.filter(SlapsComment.user_id == self.slaps_user_id).count() > 0

        if self.youtube_channel is not None:
            commented_on_youtube = YoutubeVideoComment.query.filter(
                YoutubeVideoComment.channel_id == self.youtube_channel_id).count() > 0

        return commented_on_slaps or commented_on_youtube

    @property
    def has_social_media_profile(self):
        try:
            if self.slaps_user is not None:
                return self.slaps_user.twitter_url is not None or self.slaps_user.instagram_url is not None or self.slaps_user.facebook_url is not None
            # return self.slaps_user is not None or self.youtube_channel is not None or self.facebook is not None or self.spotify is not None or self.instagram is not None or self.twitter is not None
            if self.youtube_channel is not None and self.youtube_channel.url is not None:
                return True

            if self.facebook is not None and self.facebook.url is not None:
                return True

            if self.spotify is not None and self.spotify.url is not None:
                return True

            if self.instagram is not None and self.instagram.url is not None:
                return True

            if self.twitter is not None and self.twitter.url is not None:
                return True
        except Exception as e:
            return False

    @property
    def username(self):
        """Determined by their active social media accounts"""
        if self.slaps_user_id is not None:
            return self.slaps_user.username
        if self.youtube_channel_id is not None:
            return self.youtube_channel.name
        if self.facebook_user_id is not None:
            return self.facebook.username
        if self.spotify_id is not None:
            return self.spotify.username
        if self.instagram_id is not None:
            return self.instagram.username
        if self.twitter_id is not None:
            return self.twitter.username

    @property
    def location(self):
        return self.slaps_user.location if self.slaps_user else None

    def to_dict(self):
        _messages = []
        _comments = []

        if self.slaps_user is not None:
            _messages = [message.to_dict() for message in self.slaps_user.messages]
            _comments = [comment.to_dict() for comment in self.slaps_user.comments]

        if self.youtube_channel is not None:
            _comments.extend([comment.to_dict() for comment in self.youtube_channel.comments])

        socials = {
            "youtube": self.youtube_channel.url if self.youtube_channel else None,
            "facebook": self.facebook.url if self.facebook else None,
            "spotify": self.spotify.url if self.spotify else None,
            "instagram": self.instagram.url if self.instagram else None,
            "twitter": self.twitter.url if self.twitter else None,
        }
        return dict(
            id=self.id,
            username=self.username,
            description=self.slaps_user.description if self.slaps_user else None,
            messages=_messages,
            comments=_comments,
            social_count=len(set(socials.values())),
            socials=socials,
            profile_image_url=self.profile_image_url,
            has_messaged=self.has_messaged,
            has_commented=self.has_commented,
            slaps=self.slaps_user.to_dict() if self.slaps_user else None,
            youtube=self.youtube_channel.to_dict() if self.youtube_channel else None,
            facebook=self.facebook.to_dict() if self.facebook else None,
            spotify=self.spotify.to_dict() if self.spotify else None,
            instagram=self.instagram.to_dict() if self.instagram else None,
            twitter=self.twitter.to_dict() if self.twitter else None
        )


instagram_hashtags = db.Table(
    "instagram_hashtags",
    db.Column("instagram_post_id", db.Integer, db.ForeignKey("instagram_posts.id")),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"))
)


class InstagramPost(SqlModel, SurrogatePK, TimeMixin):
    """
    An instagram post.
    """
    __tablename__ = "instagram_posts"

    url = db.Column(db.Text, nullable=False, unique=True)
    image_url = db.Column(db.Text, nullable=False)
    caption = db.Column(db.Text, nullable=True)
    tags = db.relationship("Tag", secondary=instagram_hashtags, backref="instagram_posts")
    likes_count = db.Column(db.Integer, nullable=True)
    comments_count = db.Column(db.Integer, nullable=True)

    profile_id = foreign_key("instagram_profiles", nullable=False)
    profile = db.relationship("InstagramProfile", back_populates="posts", uselist=True)

    def to_dict(self):
        return dict(
            url=self.url,
            image_url=self.image_url,
            caption=self.caption,
            likes_count=self.likes_count,
            comments_count=self.comments_count,
            profile=self.profile.to_dict(),
            tags=[tag.tag for tag in self.tags]
        )


class InstagramProfile(SqlModel, SurrogatePK, TimeMixin):
    """
    An instagram profile.
    """
    __tablename__ = "instagram_profiles"

    url = db.Column(db.Text, nullable=False, unique=True)
    username = db.Column(db.String, nullable=True, unique=False)
    profile_image_url = db.Column(db.Text, nullable=True)

    followers_count = db.Column(db.Integer, nullable=True)

    posts = db.relationship("InstagramPost", back_populates="profile", uselist=True)

    # profile_id = foreign_key("user_profiles", nullable=True)
    profile = db.relationship("UserProfile", back_populates="instagram", uselist=False)

    def to_dict(self):
        return dict(
            url=self.url,
            username=self.username,
            profile_image_url=self.profile_image_url
        )


class TwitterProfile(SqlModel, SurrogatePK, TimeMixin):
    """
    A twitter profile.
    """
    __tablename__ = "twitter_profiles"

    url = db.Column(db.Text, nullable=False, unique=True)
    username = db.Column(db.String, nullable=True, unique=False)
    profile_image_url = db.Column(db.Text, nullable=True)

    # profile_id = foreign_key("user_profiles", nullable=True)
    profile = db.relationship("UserProfile", back_populates="twitter", uselist=False, cascade="all, delete")

    def to_dict(self):
        return dict(
            url=self.url,
            username=self.username,
            profile_image_url=self.profile_image_url
        )


class SpotifyArtist(SqlModel, SurrogatePK, TimeMixin):
    """
    A spotify artist.
    """
    __tablename__ = "spotify_artists"

    url = db.Column(db.Text, nullable=False, unique=True)
    artist_id = db.Column(db.Text, nullable=True, unique=True)

    name = db.Column(db.Text, nullable=True)

    # profile_id = foreign_key("user_profiles", nullable=True)
    profile = db.relationship("UserProfile", back_populates="spotify", uselist=False, cascade="all, delete")

    tracks = db.relationship("SpotifyTrack", back_populates="artist", uselist=True, cascade="all, delete")

    def to_dict(self):
        return dict(
            url=self.url,
            artist_id=self.artist_id,
            name=self.name,
            tracks=[track.to_dict() for track in self.tracks],
        )


class SpotifyTrack(SqlModel, SurrogatePK, TimeMixin):
    """
    A spotify track.
    """

    url = db.Column(db.Text, nullable=False, unique=True)
    track_id = db.Column(db.Text, nullable=True)
    name = db.Column(db.Text, nullable=True)

    artist_id = foreign_key("spotify_artists", nullable=True)
    artist = db.relationship("SpotifyArtist", back_populates="tracks", uselist=False)

    def to_dict(self):
        return dict(
            url=self.url,
            track_id=self.track_id,
            name=self.name
        )


class ActionLog(SqlModel, SurrogatePK, TimeMixin):
    """
    A log of actions taken by the bot.
    Each entry will be unique to the action name, and have a timestamp of when the action was last completed.

    This allows behaviours in various implementations to perform "other" actions while the sleep period is active.
    """

    __tablename__ = "action_log"

    name = db.Column(db.Text, nullable=False, unique=True)
    value = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return dict(name=self.name, value=self.value, updated_at=self.updated_at)

    @staticmethod
    def has(action_name):
        return ActionLog.query.filter_by(name=action_name).first() is not None

    @staticmethod
    def get(action_name, default_value=None):
        """
        Get the value of the action.
        """
        log = ActionLog.query.filter_by(name=action_name).first()

        if log is None:
            if utils.is_iterable(default_value):
                default_value = json.dumps(default_value)

            log = ActionLog(name=action_name, value=default_value)
            log.save(commit=True)

        if log.value is None:
            log.value = json.dumps(default_value) if utils.is_iterable(default_value) else default_value
            log.save(commit=True)

        return log

    @staticmethod
    def log(action_name, value):
        log = ActionLog.get(action_name)
        if utils.is_iterable(value):
            value = json.dumps(value)
        log.value = value
        log.updated_at = datetime.datetime.utcnow()
        log.save(commit=True)

    @staticmethod
    def updated_within_range(action_name, hours_ago: int = 0, days_ago: int = 0, minutes_ago: int = 0) -> bool:
        if hours_ago is 0 and days_ago is 0 and minutes_ago is 0:
            raise ValueError("Must specify at least one of hours_ago, days_ago, or minutes_ago")
        log = ActionLog.get(action_name)
        if log is None:
            return False
        return log.last_updated_within(days=days_ago, hours_ago=hours_ago, minutes_ago=minutes_ago)


class YoutubeVideoComment(SqlModel, SurrogatePK, TimeMixin):
    __tablename__ = "youtube_comments"

    channel_id = foreign_key("youtube_channels", nullable=False)
    channel = db.relationship("YoutubeChannel", back_populates="comments")

    url = db.Column(db.Text, nullable=False)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())

    liked = db.Column(db.Boolean, nullable=True, default=False)
    subscribed = db.Column(db.Boolean, nullable=True, default=False)

    def to_dict(self):
        return dict(
            url=self.url,
            message=self.message,
            timestamp=self.timestamp,
            liked=self.liked,
            subscribed=self.subscribed
        )


class YoutubeChannel(SqlModel, SurrogatePK, TimeMixin):
    __tablename__ = "youtube_channels"

    profile = db.relationship("UserProfile", back_populates="youtube_channel", uselist=False,
                              cascade="all, delete-orphan")

    url = db.Column(db.Text, nullable=False, unique=True)
    name = db.Column(db.Text, nullable=True, unique=False)

    subscribed = db.Column(db.Boolean, default=False)
    subscribe_date = db.Column(db.DateTime, nullable=True)

    comments = db.relationship("YoutubeVideoComment", cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self):
        return dict(
            url=self.url,
            name=self.name,
            subscribed=self.subscribed,
            subscribe_date=self.subscribe_date,
            comments=[c.to_dict() for c in self.comments.all()]
        )

    def has_commented_recently(self, days=0, hours=12):
        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)

        messages_in_date_range = YoutubeVideoComment.query.filter(YoutubeVideoComment.timestamp >= days_ago,
                                                                  YoutubeVideoComment.timestamp <= start_range,
                                                                  YoutubeVideoComment.channel_id == self.id).all()
        return len(messages_in_date_range) > 0


class SoundcloudMessage(SqlModel, SurrogatePK, TimeMixin):
    """
    Soundcloud direct messages to users.
    """

    __tablename__ = "soundcloud_messages"
    user_id = foreign_key("soundcloud_users", nullable=False)
    user = db.relationship("SoundcloudUser", back_populates="messages")
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())


class SoundcloudComment(SqlModel, SurrogatePK, TimeMixin):
    """
    Soundcloud comment
    """

    __tablename__ = "soundcloud_comments"
    user_id = foreign_key("soundcloud_users", nullable=False)
    user = db.relationship("SoundcloudUser", back_populates="comments")
    url = db.Column(db.Text, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())


class SoundcloudLike(SqlModel, SurrogatePK, TimeMixin):
    """
    Soundcloud like.
    """

    __tablename__ = "soundcloud_likes"
    url = db.Column(db.Text, nullable=False, unique=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())


class FacebookUser(SqlModel, SurrogatePK, TimeMixin):
    """
    Facebook User Profile. Tracks data across the bot.
    """
    __tablename__ = "facebook_users"

    profile = db.relationship("UserProfile", back_populates="facebook", uselist=False, cascade="all, delete")

    url = db.Column(db.Text, nullable=False, unique=True)
    name = db.Column(db.Text, nullable=True, unique=True)
    messages = db.relationship("FacebookMessage", back_populates="user", cascade='all, delete-orphan')
    ignore = db.Column(db.Boolean, nullable=True, default=False)

    def to_dict(self):
        return dict(
            id=self.id,
            url=self.url,
            name=self.name,
            ignore=self.ignore,
            messages=[msg.to_dict() for msg in self.messages]
        )

    def check_message_history(self, message, similarity_max=0.75, ignore_duplicate_links=False):
        """
        Check if in all of the history between this user we've sent them a user similar to this one!
        (Easier to check all history than just last one, often times.)
        """
        if len(self.messages) == 0:
            return False

        msg_links = utils.extract_urls(message)
        for msg in self.messages:
            if ignore_duplicate_links is False and utils.message_contains_any_links(msg.message, msg_links):
                return True

            if jellyfish.jaro_winkler_similarity(msg.message, message) >= similarity_max:
                return True

        return False

    @staticmethod
    def has_sent_message(user=None, url=None, days=0, hours=12):
        if user is None:
            if url is None:
                return False
            user = FacebookUser.filter_by(url=url).first()

        if user is None:
            return False

        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)

        messages_in_date_range = FacebookMessage.query.filter(FacebookMessage.timestamp >= days_ago,
                                                              FacebookMessage.timestamp <= start_range,
                                                              FacebookMessage.user_id == user.id).all()
        return len(messages_in_date_range) > 0


class FacebookStatusEngagement(SqlModel, SurrogatePK):
    """
    A record of engagement with a status.
    """
    __tablename__ = "facebook_status_engagement"
    post_id = db.Column(db.Text, nullable=False, unique=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())

    @staticmethod
    def has_engaged_with(post_id):
        return FacebookStatusEngagement.query.filter_by(post_id=post_id).first() is not None


class FacebookMessage(SqlModel, SurrogatePK):
    """
    Represents a message sent via the bot to a user on facebook.
    """
    __tablename__ = "facebook_messages"
    user_id = db.Column(db.Integer, db.ForeignKey('facebook_users.id'), nullable=False)
    user = db.relationship('FacebookUser', back_populates="messages")
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())

    def to_dict(self):
        return dict(
            id=self.id,
            message=self.message,
            timestamp=self.timestamp
        )


class TikTokVideoLog(SqlModel, SurrogatePK, TimeMixin):
    __tablename__ = "tiktok_video_scrape_log"

    url = db.Column(db.Text, nullable=False)
    hashtag = db.Column(db.Text, nullable=False)


class ScraperLog(SqlModel, SurrogatePK, TimeMixin):
    __tablename__ = "scraper_logs"

    url = db.Column(db.Text, nullable=False)
    collected_user_count = db.Column(db.Integer, default=0)
    user_ids = db.Column(db.PickleType, nullable=True)


class SoundcloudUser(SqlModel, SurrogatePK, TimeMixin):
    __tablename__ = "soundcloud_users"

    """
    Soundcloud user profile. Tracks data across the bot
    """
    __tablename__ = "soundcloud_users"
    id = db.Column(db.Integer, primary_key=True)

    url = db.Column(db.Text, nullable=False, unique=True)
    name = db.Column(db.Text, nullable=False)
    messages = db.relationship("SoundcloudMessage", backref="soundcloud_user", lazy="dynamic",
                               cascade="all, delete-orphan")
    comments = db.relationship("SoundcloudComment", backref="soundcloud_user", lazy="dynamic",
                               cascade="all, delete-orphan")

    @staticmethod
    def has_commented_on_recently(url, days):
        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        comments_in_date_range = SoundcloudComment.query.filter(SoundcloudComment.timestamp >= days_ago,
                                                                SoundcloudComment.timestamp <= start_range,
                                                                SoundcloudComment.url == url).all()
        return len(comments_in_date_range) > 0

    @staticmethod
    def has_messaged_recently(user, days):
        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        messages_in_date_range = SoundcloudMessage.query.filter(SoundcloudMessage.timestamp >= days_ago,
                                                                SoundcloudMessage.timestamp <= start_range,
                                                                SoundcloudMessage.user == user).all()
        return len(messages_in_date_range) > 0


class SlapsUser(SqlModel, SurrogatePK, TimeMixin):
    """
    SlapsUser information collected.
    """
    __tablename__ = "users"

    profile = db.relationship("UserProfile", back_populates="slaps_user", uselist=False, cascade="all, delete-orphan")

    profile_url = db.Column(db.String, unique=True, nullable=True)
    username = db.Column(db.String, nullable=False)
    message_url = db.Column(db.String, nullable=True)

    following_on_slaps = db.Column(db.Boolean, default=False)

    twitter_url = db.Column(db.String, nullable=True)
    instagram_url = db.Column(db.String, nullable=True)
    youtube_url = db.Column(db.String, nullable=True)
    facebook_url = db.Column(db.String, nullable=True)

    messages = db.relationship("SlapsDirectMessage", back_populates="user", cascade="all, delete-orphan")
    comments = db.relationship("SlapsComment", back_populates="user", cascade="all, delete-orphan")

    description = db.Column(db.Text, nullable=True)

    deep_scraped = db.Column(db.Boolean, default=False)
    deep_scrape_completion_timestamp = db.Column(db.DateTime, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    recently_posted = db.Column(db.Boolean, default=False)
    joined_date = db.Column(db.Text, default=False, nullable=True)
    play_count = db.Column(db.Integer, default=0, nullable=True)
    follower_count = db.Column(db.Integer, default=0, nullable=True)

    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    location = db.relationship('Location', backref="users")

    def to_dict(self):
        return dict(
            id=self.id,
            profile_url=self.profile_url,
            username=self.username,
            message_url=self.message_url,
            following_on_slaps=self.following_on_slaps,
            twitter_url=self.twitter_url,
            instagram_url=self.instagram_url,
            youtube_url=self.youtube_url,
            facebook_url=self.facebook_url,
            description=self.description,
            deep_scraped=self.deep_scraped,
            messages=[message.to_dict() for message in self.messages],
            comments=[comment.to_dict() for comment in self.comments],
            profile_image_url=self.profile_image_url,
            recently_active=self.recently_posted,
            follower_count=self.follower_count,
            uploads=[upload.to_dict() for upload in self.uploads],
            location=self.location.name if self.location is not None else None
        )

    @property
    def followers_url(self):
        return f"{self.profile_url}/followers"

    @property
    def following_url(self):
        return f"{self.profile_url}/following"

    @property
    def uuid(self):
        if self.message_url is not None:
            return self.message_url.split("?to=")[-1]
        return None

    @staticmethod
    def find_or_create(slaps_url, username):
        user = SlapsUser.query.filter_by(profile_url=slaps_url).first()

        if user is None:
            user = SlapsUser(profile_url=slaps_url, username=username)
            user.save(commit=True)
            utils.debug(f"+ Created new user: {user.username} ({user.profile_url})")

        return user

    @staticmethod
    def has_deep_scraped(user, days, hours):
        if user.deep_scrape_completion_timestamp is None:
            return False
        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)
        return days_ago <= user.deep_scrape_completion_timestamp <= start_range

    @staticmethod
    def has_sent_message(user=None, url=None, days=0, hours=12):
        if user is None:
            if url is None:
                return False
            user = SlapsUser.filter_by(profile_url=url).first()

        if user is None:
            return False

        if user.message_url is None:
            return False

        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=int(days), hours=int(hours))

        for message in user.messages:
            if days_ago <= message.timestamp <= start_range:
                return True

        return False

        # messages_in_date_range = SlapsDirectMessage.query.filter(SlapsDirectMessage.timestamp >= days_ago,
        #                                                          SlapsDirectMessage.timestamp <= start_range,
        #                                                          SlapsDirectMessage.user_id == user.id).all()
        # return len(messages_in_date_range) > 0

    @staticmethod
    def has_commented(user, days=0, hours=12):
        if user is None:
            raise Exception("Cannot check if user has commented without a user")

        if SlapsComment.query.filter_by(user_id=user.id).first() is None:
            return False

        start_range = datetime.datetime.utcnow()
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=days, hours=hours)

        messages_in_date_range = SlapsComment.query.filter(SlapsComment.timestamp >= days_ago,
                                                           SlapsComment.timestamp <= start_range,
                                                           SlapsComment.user_id == user.id).all()
        return len(messages_in_date_range) > 0

    @classmethod
    def get_random_user(cls):
        return cls.get_random()

    @classmethod
    def get_random_unmessaged_user(cls, days: int, hours: int, depth=0):
        user = cls.get_random_user()
        if depth > 3:
            return None
        if user is None or user.message_url is None or user.following_on_slaps is False or user.profile_url is None:
            return cls.get_random_unmessaged_user(days=days, hours=hours, depth=depth + 1)

        if SlapsUser.has_sent_message(user=user, days=days, hours=hours):
            return cls.get_random_unmessaged_user(days=days, hours=hours, depth=depth + 1)

        return user

    def message(self, message, received=False):
        _msg = SlapsDirectMessage(user=self, message=message, timestamp=datetime.datetime.utcnow(), received=received)
        _msg.save(commit=True)

    def comment(self, comment, title=None):
        _comment = SlapsComment(user=self, comment=comment, timestamp=datetime.datetime.utcnow(), title=title)
        _comment.save(commit=True)


slaps_user_uploads_tags = db.Table('slaps_user_uploads_tags',
                                   db.Column('slaps_user_upload_id', db.Integer, db.ForeignKey('slaps_user_upload.id')),
                                   db.Column('tag_id', db.Integer, db.ForeignKey('tags.id')))


class SlapsUserUpload(SqlModel, SurrogatePK):
    __tablename__ = "slaps_user_upload"

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('SlapsUser', backref="uploads", cascade="all,delete")

    track_url = db.Column(db.String, nullable=False)
    media_url = db.Column(db.Text, nullable=True, default=None)
    track_title = db.Column(db.String, nullable=False)
    artwork_url = db.Column(db.Text, nullable=True, default=None)

    description = db.Column(db.Text, nullable=True, default=None)

    tags = db.relationship("Tag", secondary=slaps_user_uploads_tags, backref="slaps")

    # todo implement play count, like count, and comments

    def to_dict(self):
        return dict(
            id=self.id,
            user_id=self.user_id,
            track_url=self.track_url,
            media_url=self.media_url,
            track_title=self.track_title,
            description=self.description,
            artwork_url=self.artwork_url,
            tags=[tag.tag for tag in self.tags]
        )


class SlapsDirectMessage(SqlModel, SurrogatePK):
    __tablename__ = "messages"
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('SlapsUser', back_populates="messages")
    message = db.Column(db.Text, nullable=False)
    message_id = db.Column(db.Text, nullable=True, default=None)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())
    received = db.Column(db.Boolean, nullable=True, default=False)

    def to_dict(self):
        return dict(
            id=self.id,
            user_id=self.user_id,
            username=self.user.username,
            profile_pic_url=self.user.profile_url,
            message=self.message,
            timestamp=self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            received=self.received
        )


class SlapsComment(SqlModel, SurrogatePK):
    __tablename__ = "slaps_comments"
    title = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('SlapsUser', back_populates="comments", cascade="all,delete")
    comment = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow())
    song_id = db.Column(db.Text, nullable=True, unique=False)

    def to_dict(self):
        return dict(
            id=self.id,
            user_id=self.user_id,
            title=self.title,
            comment=self.comment,
            timestamp=self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            song_id=self.song_id
        )

    @staticmethod
    def has_commented_on(user: SlapsUser, title: str):
        return SlapsComment.query.filter_by(title=title, user_id=user.id).first() is not None
