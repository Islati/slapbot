import random
import time
from multiprocessing import cpu_count
from pathlib import Path
from typing import List

import click
import typer
from slapbot import create_app
from slapbot.bots import DriverType
from slapbot.bots.facebook import FacebookBot
from slapbot.bots.slaps import SlapBot
from slapbot.bots.ytbot import YoutubeBot
from slapbot.config import Config
from slapbot.models import SlapsUser

flask_app = create_app(Config())
bot = None

cli = typer.Typer()


def run_slapbot(slapbot):
    slapbot.begin()
    sleep_time = slapbot.get_random_messaging_sleep_time()
    print(f"Sleeping after complete run for {sleep_time}s")
    time.sleep(sleep_time)


@cli.command()
def test_get_random_slaps_user(amount: int = typer.Option(100, help="Amount of users to get."),
                               days: int = typer.Option(30, help="Days to check for new users."),
                               hours: int = typer.Option(0, help="Hours to check for new users.")):
    retreived_users = 0
    while retreived_users < amount:
        user: SlapsUser = SlapsUser.get_random_unmessaged_user(days=7, hours=0)
        if user.message_url is None or user.following_on_slaps is False or user.profile_url is None:
            continue
        if user is None:
            print("No users found.")
            return
        try:
            print(f"User: {user.username} @ {user.profile_url}")
        except:
            continue

        retreived_users += 1


@cli.command()
def slaps(headless: bool = False, driver: str = "FireFox"):
    """Run SlapBot."""
    if driver is None:
        click.secho(f"Supported drivers are: Chrome, FireFox, UC", fg="red")
        return

    driver_type = None
    match driver.lower():
        case "firefox":
            driver_type = DriverType.FIREFOX
        case "chrome":
            driver_type = DriverType.CHROME
        case "uc":
            driver_type = DriverType.UNDETECTED_CHROME
        case _:
            click.secho(f"Supported drivers are: Chrome, FireFox, uc (undetected chrome)", fg="red")
            return

    bot = SlapBot(headless=headless, driver_type=driver_type)

    while True:
        if headless is True:
            print(f"Running slapbot in headless mode.")
        run_slapbot(slapbot=bot)

        time.sleep(random.randint(
            bot.config.get('finish_restart_wait_time_min', 4500),
            bot.config.get('finish_restart_wait_time_max', 6000)
        ))


@cli.command()
def youtube():
    """Run the YouTube bot. Only supports FireFox
    Place geckodriver in the root folder of slapbot (same folder as this file) to run it"""
    youtube_bot = YoutubeBot()
    youtube_bot.begin()


@cli.command()
def facebook(headless: bool = False, force_indexing: bool = False):
    """Run the Facebook bot."""
    facebook_bot = FacebookBot(headless=headless)

    if force_indexing is True:
        facebook_bot.force_friend_indexing = True
        facebook_bot.debug("~ Force indexing of friends list enabled. [FLAG]")

    facebook_bot.begin()


@cli.command()
def backend():
    """
    This command provides the rest server for the dashboard. Absolutely f'n gas.
    """
    flask_app.run(debug=True)


@cli.command()
def create_profiles(users: str = typer.Option(None, help="Comma seperated list of users to fix."),
                    social: str = typer.Option("slaps",
                                               help="The social network to link profiles for. Supported: Slaps, Profiles"),
                    threaded: bool = typer.Option(True, help="Whether or not to run threaded."),
                    threads: int = typer.Option(cpu_count(), help="Number of threads to use for fixing profiles.")):
    """Link profiles. Used in the dashboard."""
    print(users)
    match social.lower():
        case "slaps":
            from slapbot.cli.fix_profiles import update_with_slaps
            update_with_slaps(users=users.split(',') if users is not None else None)
        case _:
            pass


@cli.command()
def update_profiles(users: str = typer.Option(None, help="Comma seperated list of users to fix."),
                    social: str = typer.Option("slaps",
                                               help="The social network to fix profiles for. Supported: Facebook, YouTube, Slaps"),
                    driver: str = typer.Option("FireFox", help="The driver to use. Supported: Chrome, FireFox, UC"),
                    headless: bool = typer.Option(True, help="Whether or not to run headless."),
                    days: int = typer.Option(7, help="Number of days to check for new profiles."),
                    threads: int = typer.Option(cpu_count(), help="Number of threads to use for fixing profiles."),
                    all_users: bool = typer.Option(False, help="Whether or not to update all users.")):
    """
    Update user profiles by scraping them for new information.
    """
    click.secho(f"Updating profiles for {social} / users {users}...", fg="green")

    """Run SlapBot."""
    if driver is None:
        click.secho(f"Supported drivers are: Chrome, FireFox, UC", fg="red")
        return

    driver_type = None
    match driver.lower():
        case "firefox":
            driver_type = DriverType.FIREFOX
        case "chrome":
            driver_type = DriverType.CHROME
        case "uc":
            driver_type = DriverType.UNDETECTED_CHROME
        case _:
            click.secho(f"Supported drivers are: Chrome, FireFox, uc (undetected chrome)", fg="red")
            return

    match social.lower():
        case "facebook", "fb":
            click.secho("Facebook is not supported yet.", fg="red")
        case "youtube", "yt":
            click.secho("YouTube is not supported yet.", fg="red")
        case "slaps":
            from slapbot.cli.update_profiles import update_slaps_data
            update_slaps_data(headless=headless, threads=threads, driver_type=driver_type,
                              users=users.split(',') if users is not None else None, all_users=all_users, days=days)
        case _:
            click.secho(f"Supported social networks are: Facebook, YouTube, Slaps", fg="red")
            return


if __name__ == "__main__":
    cli()
