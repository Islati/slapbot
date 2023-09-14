import json
import logging
import os
import random
import re
import traceback
from collections.abc import Iterable

import click
import spintax
from tqdm import tqdm
import copy

import slapbot.logging


class Singleton(object):
    """
    Having a class subclass Singleton means it will only ever be instantiated once.
    To prevent duplicate initialization of variables on class instantiation, we use the init() method.
    """

    def __new__(cls, *args, **kwds):
        it = cls.__dict__.get("__it__")
        if it is not None:
            return it
        cls.__it__ = it = object.__new__(cls)
        it.init(*args, **kwds)
        return it

    def init(self, *args, **kwds):
        pass


class __debugger(Singleton):
    """
    Debug class for message handling accross the application
    """

    debug_silence = False
    prefix = ""

    def init(self):
        self.debug_silence = False

        if not slapbot.logging.setup_logging(console_log_output="stdout", console_log_level="debug",
                                             console_log_color=True,
                                             logfile_file=f'debugger.log', logfile_log_level="debug",
                                             logfile_log_color=False,
                                             log_line_template="%(color_on)s[%(created)d] [%(threadName)s] [%(levelname)-8s] %(message)s%(color_off)s"):
            click.secho(f"Aborting: Failed ot setup logging in `utils.debugger`::init ", fg="red")
            exit(-9)
            return

    def debug(self, text: str, msg_type="info", progress_bar: tqdm = None, fg=None, bg=None, bold=None, underline=None,
              blink=None, reverse=None, reset=None, println=False):
        try:
            text = click.style(text, fg=fg, bg=bg, bold=bold, underline=underline, blink=blink, reverse=reverse,
                               reset=reset)
        except:
            text = click.style(text.encode("utf-8"), fg=fg, bg=bg, bold=bold, underline=underline, blink=blink,
                               reverse=reverse, reset=reset)

        if self.debug_silence is True and println is False:
            if progress_bar is not None:
                progress_bar.set_description(text)
            return

        try:
            if msg_type == "debug":
                logging.debug(text)
            elif msg_type == "error":
                logging.error(text)
            elif msg_type == "info":
                logging.info(text)
            elif msg_type == "warning":
                logging.warning(text)

            if progress_bar is not None and not println:
                progress_bar.set_description(text)
        except:
            pass


debugger = __debugger()


def debug(text: str, msg_type="info", progress_bar: tqdm = None, fg=None, bg=None, bold=None, underline=None,
          blink=None, reverse=None, reset=None, println=False):
    debugger.debug(text, msg_type, progress_bar, fg, bg, bold, underline, blink, reverse, reset, println=println)


def message_contains_any_links(message: str, links: set) -> bool:
    """
    Check whether or not the message (string) contains ANY of the urls provided in the set.
    """
    return any(link in message for link in links)


DictProxyType = type(object.__dict__)


def is_iterable(obj) -> bool:
    return isinstance(obj, Iterable)


def make_hash(o):
    """
    Makes a hash from a dictionary, list, tuple or set to any level, that
    contains only other hashable types (including any lists, tuples, sets, and
    dictionaries). In the case where other kinds of objects (like classes) need
    to be hashed, pass in a collection of object attributes that are pertinent.
    For example, a class can be hashed in this fashion:

      make_hash([cls.__dict__, cls.__name__])

    A function can be hashed like so:

      make_hash([fn.__dict__, fn.__code__])
    """

    if isinstance(o, (set, tuple, list)):
        return tuple(make_hash(e) for e in o)

    if not isinstance(o, dict):
        return hash(o)

    return hash(frozenset((k, make_hash(v)) for k, v in o.items() if not k.startswith("__")))

def substrings_between(content, search, send):
    """
    Retrieve substrings between two other strings.
    Eg <abc>TEST</abc><abc>TEST2</abc>
    Would extract [TEST,TEST2]
    :param content:
    :param search:
    :param send:
    :return:
    """
    substrings = []
    int_index = 0
    string_length = len(content)

    while int_index < string_length:
        int_index_1 = content.find(search, int_index)
        if int_index_1 == -1:
            break

        int_index_1 += len(search)
        int_index_2 = content.find(send, int_index_1)
        if int_index_2 == -1:
            break

        subsequence = content[int_index_1:int_index_2]
        substrings.append(subsequence)
        int_index = int_index_2 + len(send)

    return substrings

# def substrings_between(content, search, send):
#     """
#     Retrieve substrings between two other strings.
#     Eg <abc>TEST</abc><abc>TEST2</abc>
#     Would extract [TEST,TEST2]
#     :param content:
#     :param search:
#     :param send:
#     :return:
#     """
#     substrings = []
#     int_index = 0
#     string_length = len(content)
#     continue_loop = 1
#
#     while int_index < string_length and continue_loop == 1:
#         int_index_1 = content.find(search, int_index)
#         if int_index_1 != -1:  # The substring was found, lets proceed
#             int_index_1 = int_index_1 + len(search)
#             int_index_2 = content.find(send, int_index_1)
#             if int_index_2 != -1:
#                 subsequence = content[int_index_1:int_index_2]
#                 substrings.append(subsequence)
#                 int_index = int_index_2 + len(send)
#             else:
#                 continue_loop = 0
#         else:
#             continue_loop = 0
#     return substrings


def load_text_file_to_array(file_name):
    """
    Load text file into array.
    :param file_name:
    :return:
    """
    _data = []
    with open(file_name, 'r') as file:
        _data = file.readlines()

    return _data


def load_json_file(file_name):
    """
    Load a json file from the current working directory and return its contents.
    """

    log_file_path = os.path.join(os.getcwd(), file_name)

    if not os.path.exists(log_file_path):
        return

    with open(log_file_path, "r") as log_file:
        log = json.load(log_file)

    return log


def extract_urls(string) -> list:
    """
    Using regular expressions look for URLs inside a string & return them.
    """

    return re.findall(r'(https?://\S+)', string)


def has_urls(string) -> bool:
    """
    Check whether or not the string has urls.
    """
    return len(extract_urls(string)) > 0


def save_json_file(file_name, data):
    log_file_path = os.path.join(os.getcwd(), file_name)

    with open(log_file_path, 'w+') as log_file:
        log_file.writelines(json.dumps(data, indent=4, sort_keys=True))


def load_config(config_file_name, default_config):
    """
    Called from inside startup to load configuration from the system at runtime.
    :return:
    """

    # Todo implement key comparison. Make sure structure is complete

    expected_config_path = os.path.join(os.getcwd(), config_file_name)

    # If the file doesn't exist then it's a write to the file.
    if not os.path.exists(expected_config_path):
        with open(expected_config_path, 'w+') as config_file:
            config_str = json.dumps(default_config, indent=4, sort_keys=True)
            config_file.writelines(config_str)

            return default_config

    _config = None
    with open(expected_config_path, 'r') as config_file:
        _config = json.load(config_file)

    return _config


def parse_spintax_sections(comment: str, author_name=None, song_title=None, **kwargs):
    """
    Replace the spintax sections inside the text with evaluated results
    """

    return spintax.spin(
        comment.replace('[author]', author_name if author_name else '').replace('[song]',
                                                                                song_title if song_title else ''))


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def parse_tag_descriptions(text: str, recursions=10, tags_to_query: dict = None):
    """
    Parse all the tag descriptions in the text. Multiple recursions allow nested tags to be reached.
    """
    for _ in range(recursions):
        for tag, values in tags_to_query.items():
            replacement_tag = f"[{tag}]"
            while replacement_tag in text:
                selected_replacement_value = random.choice(values)
                text = text.replace(replacement_tag, selected_replacement_value, 1)

    return text


def select_tag_description(tag: str, tags_to_query: dict = None):
    """
    Retrieve a random descriptive text value from the given tag.

    Values and tags are stored in the applications config, which is also available on disk
    in the 'config.json' file.
    """

    if tag not in tags_to_query:
        return None

    return random.choice(tags_to_query[tag.replace("[", "").replace("]", "")])


def generate_comment_using_spintax(text: str, tags_to_query: dict, author_name=None, song_title=None, trim=True):
    """
    Genearate a comment from the given text using spintax and tag descriptions.
    """
    comment = None

    try:
        comment = parse_tag_descriptions(text, tags_to_query=tags_to_query, recursions=10)
    except Exception as ex:
        raise

    try:
        comment = parse_spintax_sections(comment, author_name=author_name)
    except Exception as ex:
        raise

    try:
        comment = comment.replace("{", "").replace("}", "").replace("[author]",
                                                                    author_name if author_name is not None else "").replace(
            "[song]", song_title if song_title is not None else "").replace("|", "").replace("\\", "")

        while '  ' in comment:
            comment = comment.replace('  ', ' ')
    except Exception as ex:
        raise

    if comment is None:
        raise Exception("Error generating comment")

    return comment.replace("&quot;", "\\").replace("{", "").replace("}", "").replace("|", "") if trim else comment
