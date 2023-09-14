"""
Link profiles to users and update profiles with new information.
"""
import datetime
from multiprocessing import cpu_count
from threading import Thread

import click
import timeago

from slapbot.app import app
from slapbot.models import SlapsUser, YoutubeChannel, TwitterProfile, InstagramProfile, FacebookUser, UserProfile


def update_with_slaps(users=None):
    """Update profiles with new information from Slaps."""

    def process_users(offset=0,limit=100, users=None):
        with app.app_context():
            users = SlapsUser.query.offset(offset).limit(limit).all() if users is None else users
            click.secho(f"~ Processing {len(users)} users from offset {offset}.", fg="green")

            for user in users:
                if isinstance(user, str):
                    user = SlapsUser.query.filter_by(username=user).first()
                    click.secho(f"~ Processing {user.username}", fg="green")

                try:
                    if user is None:
                        continue

                    if user.profile is None:
                        user.profile = UserProfile(slaps_user=user).save(commit=True)

                    profile = user.profile

                    if profile.youtube_channel is None and user.youtube_url is not None:
                        profile.youtube_channel = YoutubeChannel(url=user.youtube_url).save(commit=True)
                        click.secho(f"~ Updated youtube for {user.username}", fg="red")

                    if profile.twitter is None and user.twitter_url is not None:
                        profile.twitter = TwitterProfile(url=user.twitter_url).save(commit=True)
                        click.secho(f"~ Updated twitter for {user.username}", fg="cyan")

                    if profile.instagram is None and user.instagram_url is not None:
                        profile.instagram = InstagramProfile(url=user.instagram_url).save(commit=True)
                        click.secho(f"~ Updated instagram for {user.username}", fg="magenta")

                    if profile.facebook is None and user.facebook_url is not None:
                        profile.facebook = FacebookUser(url=user.facebook_url).save(commit=True)
                        click.secho(f"~ Updated facebook for {user.username}", fg="blue")

                    if profile.profile_image_url is None and user.profile_image_url is not None:
                        profile.profile_image_url = user.profile_image_url
                        click.secho(f"~ Updated profile image for {user.username}", fg="white",bold=True)

                    profile.save(commit=True)
                except:
                    continue

    total_users = SlapsUser.query.count() if users is None else len(users)
    pages = cpu_count() * 2

    users_per_page = total_users / pages

    active_threads = []

    click.secho(f"~ Processing {total_users} users over {pages} pages w/ {users_per_page} users per page", fg="green")
    start_time = datetime.datetime.now()

    for page in range(0,pages):
        click.secho(f"~ Starting thread {page}", fg="green")
        offset = page * users_per_page

        thread = Thread(target=process_users, args=(offset, users_per_page,users))
        active_threads.append(thread)
        thread.start()

    for thread in active_threads:
        thread.join()

    time_elapsed = datetime.datetime.now() - start_time

    click.secho(f"~ Done processing {total_users} users in {time_elapsed.seconds / 60}s", fg="green")