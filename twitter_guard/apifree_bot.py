import os
import sys
import traceback

import requests

from urllib.parse import urlencode, quote, unquote
from urllib.request import urlopen, Request
import http.cookiejar

from dataclasses import dataclass, field, asdict as dtc_asdict
from functools import cache

from datetime import datetime, timezone
from dateutil import tz

import yaml
import json

import pickle
import random
import re
import secrets
import copy

from .selenium_bot import SeleniumTwitterBot
from .utils import *
from .rule_parser import rule_eval
from .session import CustomSession as Session

# from .reporter import ReportHandler
from time import sleep

from collections import abc
import keyword

from http.client import HTTPConnection

import logging

logger = logging.getLogger(__name__)


def drop_accept_encoding_on_putheader(http_connection_putheader):
    def wrapper(self, header, *values):
        if header == "Accept-Encoding" and "identity" in values:
            return
        return http_connection_putheader(self, header, *values)

    return wrapper

# this will avoid python automatically add Accept-Encoding: identity
HTTPConnection.putheader = drop_accept_encoding_on_putheader(HTTPConnection.putheader)

def display_session_cookies(s):
    logger.info("print cookies")
    for x in s.cookies:
        logger.debug(f"{x}")

def make_cookie_string(session_cookies):
    cookie_strings = []

    # Iterate through the cookies and build cookie strings
    for cookie_name, cookie_value in session_cookies.items():
        cookie_string = f"{cookie_name}={cookie_value}"
        cookie_strings.append(cookie_string)

    # Join the cookie strings using the ";" separator
    cookies_string_with_separator = "; ".join(cookie_strings)
    return cookies_string_with_separator


def set_cookies_from_headers(headers_list, session=None):
    # headers_list: from getheaders()
    cookies = {x[1].split("=")[0]: "=".join(x[1].split("=")[1:]).split(";")[0] for x in headers_list if x[0] == "set-cookie"}
    for key in cookies:
        session.cookies.set(key, cookies[key])


def urllib_post(url, headers=None, payload=None, session=None):
    # add cookie string
    cookie_string = make_cookie_string(session.cookies)
    headers["Cookie"] = cookie_string

    req = Request(url, headers=headers, method="POST", data=json.dumps(payload).encode("utf-8"))
    with urlopen(req, timeout=10) as response:
        headers = response.headers
        status_code = response.status
        content = response.read()
        headers_list = response.getheaders()
        set_cookies_from_headers(headers_list, session=session)

        # Create a requests Response object
        r = requests.Response()
        # Populate the requests Response object with data
        r.url = url
        r.status_code = status_code
        r.headers = headers
        r._content = content
        return r


def genct0():
    """
    Generated the ct0 cookie value.
    Uses the method used in the js file of the website.
    """

    random_value = secrets.token_bytes(32)

    s = ""
    for c in random_value:
        s += hex(c)[-1]

    return s


def oracle(user, filtering_rule):
    default_rule = "(followers_count < 5) or (days < 180)"
    rule_eval_vars = {
        "followers_count": user.followers_count,
        "following_count": user.following_count,
        "tweet_count": user.tweet_count,
        "days": user.days_since_registration,
        "favourites_count": user.favourites_count,
        "media_count": user.media_count,
    }

    try:
        result = rule_eval(filtering_rule, rule_eval_vars)
    except:
        traceback.print_exc()
        result = rule_eval(default_rule, rule_eval_vars)

    return result


class TwitterJSON:
    def __new__(cls, arg):
        if isinstance(arg, abc.Mapping) or arg is None:
            return super().__new__(cls)  # object.__new__(TwitterJSON)
        elif isinstance(arg, abc.MutableSequence):
            return [cls(item) for item in arg]
        else:
            return arg

    def __init__(self, mapping):
        if mapping is None:
            self.__data = None
            return
        self.__data = {}
        for key, value in mapping.items():
            if keyword.iskeyword(key):
                key += "_"
            self.__data[key] = value

    def __getattr__(self, name):  # only called when the named attribute could not be found
        try:
            # convert the mangled __typename back to original value
            if "__typename" in name:
                name = "__typename"
            # no ambiguity: when we refer to items, we refer to a field, not the items() method
            if name != "items":
                return getattr(self.__data, name)
            # we are only in the data, not the built-in method
            else:
                raise AttributeError
        except AttributeError:
            if self.__data is None:
                return TwitterJSON(None)  # calling dot on an instance of None data returns another instance of None data
            if name in self.__data:
                return TwitterJSON(self.__data[name])
            return TwitterJSON(None)

    # still supports subscription, just in case
    def __getitem__(self, name):
        return self.__getattr__(name)

    def __dir__(self):
        return self.__data.keys()

    def __repr__(self):
        return str(self.__data)

    def __len__(self):
        """
        if __bool__ is not implemented, Python tries to invoke x.__len__(), and if that returns  zero, bool returns False.
        """
        if self.__data is None:
            return 0
        return len(self.__data)

    def __contains__(self, key):
        """
        called when `in` operation is used.
        """
        return key in self.__data

    def __iter__(self):
        return (key for key in self.__data)

    def __eq__(self, other):
        # vs None: return True for TwitterJSON(None)
        if other is None and self.__data is None:
            return True
        # vs other TwitterJSON object
        if isinstance(other, TwitterJSON):
            return self.__data == other._TwitterJSON__data
        return False

    def values(self):
        return (TwitterJSON(x) for x in self.__data.values())


@dataclass
class TwitterUserProfile:
    user_id: int
    screen_name: str
    created_at: str = field(default=None)
    following_count: int = field(default=None)
    followers_count: int = field(default=None)
    tweet_count: int = field(default=None)
    media_count: int = field(default=None)
    favourites_count: int = field(default=None)
    days_since_registration: int = field(init=False, default=None)
    display_name: str = field(default=None, metadata={"keyword_only": True})
    blocked: bool = field(default=None)

    def __post_init__(self):
        if self.created_at is not None:
            current_time = datetime.now(timezone.utc)
            created_time = datetime.strptime(self.created_at, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=timezone.utc).astimezone(tz.gettz())
            time_diff = current_time - created_time
            self.days_since_registration = time_diff.days


@dataclass
class Tweet:
    tweet_id: int
    tweet_type: str = field(default=None)
    created_at: str = field(default=None)
    source: str = field(default=None)
    text: str = field(default=None)
    lang: str = field(default=None)
    hashtags: list = field(default=None)
    media: list = field(default=None, repr=False)
    user_mentions: list = field(default=None)
    quoted_tweet_id: int = field(default=None, repr=False)
    quoted_user_id: int = field(default=None, repr=False)
    replied_tweet_id: int = field(default=None, repr=False)
    replied_user_id: int = field(default=None, repr=False)
    retweeted_tweet_id: int = field(default=None, repr=False)
    retweeted_user_id: int = field(default=None, repr=False)

    view_count: int = field(default=None)
    reply_count: int = field(default=None)
    retweet_count: int = field(default=None)
    favorite_count: int = field(default=None)
    quote_count: int = field(default=None)
    bookmark_count: int = field(default=None)

    user: TwitterUserProfile = field(default=None)

    def __post_init__(self):
        if self.view_count:
            self.view_count = int(self.view_count)


@dataclass
class TwitterList:
    list_id: int
    name: str = field(default=None)
    description: str = field(default=None)
    member_count: int = field(default=None)
    subscriber_count: int = field(default=None)
    user: TwitterUserProfile = field(default=None)


class SessionType:
    Authenticated = "Authenticated"
    Guest = "Guest"


class TwitterLoginBot:
    def __init__(self, email, password, screenname, phonenumber=None, cookie_path=None):
        self._headers = {
            "Host": "api.twitter.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            # "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://twitter.com/",
            # "x-twitter-polling": "true",
            # "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "x-twitter-active-user": "yes",
            "Origin": "https://twitter.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "Connection": "keep-alive",
            "TE": "trailers",
            # "X-Client-Uuid": "d1ea869c-5118-4a8b-8e21-2c7620f0e84d",
        }

        self._session = Session()#requests.Session()

        self._cookie_path = cookie_path

        self._email = email
        self._password = password
        self._screenname = screenname
        self._phonenumber = phonenumber

        self._init_forms()

        # get the flow_token
        self.get_login_flow_token()

        while int(self.login_flow_token.split(":")[-1]) != 13:
            self._do_task()

        # one more time to get longer ct0
        logger.debug("update to full ct0")
        self._do_task()

        # save the cookies for reuse
        self.save_cookies()

    def _init_forms(self):
        self.get_token_payload = {
            "input_flow_data": {
                "flow_context": {
                    "debug_overrides": {},
                    "start_location": {"location": "manual_link"},
                }
            },
            "subtask_versions": {
                "action_list": 2,
                "alert_dialog": 1,
                "app_download_cta": 1,
                "check_logged_in_account": 1,
                "choice_selection": 3,
                "contacts_live_sync_permission_prompt": 0,
                "cta": 7,
                "email_verification": 2,
                "end_flow": 1,
                "enter_date": 1,
                "enter_email": 2,
                "enter_password": 5,
                "enter_phone": 2,
                "enter_recaptcha": 1,
                "enter_text": 5,
                "enter_username": 2,
                "generic_urt": 3,
                "in_app_notification": 1,
                "interest_picker": 3,
                "js_instrumentation": 1,
                "menu_dialog": 1,
                "notifications_permission_prompt": 2,
                "open_account": 2,
                "open_home_timeline": 1,
                "open_link": 1,
                "phone_verification": 4,
                "privacy_options": 1,
                "security_key": 3,
                "select_avatar": 4,
                "select_banner": 2,
                "settings_list": 7,
                "show_code": 1,
                "sign_up": 2,
                "sign_up_review": 4,
                "tweet_selection_urt": 1,
                "update_users": 1,
                "upload_media": 1,
                "user_recommendations_list": 4,
                "user_recommendations_urt": 1,
                "wait_spinner": 3,
                "web_modal": 1,
            },
        }

        self.get_sso_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:0",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginJsInstrumentationSubtask",
                    "js_instrumentation": {
                        "response": '{"rf":{"ae0c387278259a55d975ad389656c366bb247af661b87720a61ef1f00415a074":-1,"a08bdec063bd39221c4a9ed88833e66ed219aa1b1ffffbb689c7e878b77ed9c5":170,"a406e976cde22b2559c171f75fdb53d08cdec1b36eca8a157a8f8d535e5c4cfa":-12,"ec40d46fc7ad9581fc9c23c52181d7a1bb69fa94278a883ed01a381b4a0fe4d7":224},"s":"1pN0NCz6xs95SmhDHPdYrjG_zpdLJkzjMO8oTRG2VzM6oiyEuGIZFpGKUDLlNdVqJwMOIqLTOvnRQI860XuhPuft1-jMyHl_2rJGwyXKl2gcIP9lulFs39K9uRdaVfZK6UDmC_fWtbqJpiUt5DapQNK0T6wwq0PIAZG28cXYTveoiBZBJz3e3_fzUJYbSuYWZviw9W_M_AE3PAtFvF2294NwFENJ6n3DkNi-yaBVYq9nOeTieVGSiw_TdxnDGmd76yimmLpfD1yJFVDA1Z2WRy0ytCCzWjWck0MJuq1cBc1JpV9Jhjk_sPqqlKQiiG2pdbR5NP4fSN-AIa1luCSywwAAAYZcVUO7"}',
                        "link": "next_link",
                    },
                }
            ],
        }

        self.account_duplication_check_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:7",
            "subtask_inputs": [
                {
                    "subtask_id": "AccountDuplicationCheck",
                    "check_logged_in_account": {"link": "AccountDuplicationCheck_false"},
                }
            ],
        }

        self.get_full_ct0_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:13",
            "subtask_inputs": [],
        }

        self.enter_email_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:1",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginEnterUserIdentifierSSO",
                    "settings_list": {
                        "setting_responses": [
                            {
                                "key": "user_identifier",
                                "response_data": {"text_data": {"result": self._email}},
                            }
                        ],
                        "link": "next_link",
                    },
                }
            ],
        }

        self.enter_alternative_id_payload = {
            "flow_token": "g;167669570499095475:-1676695708216:wfmlDaSgvN5ydOS4EI5oJvr6:5",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginEnterAlternateIdentifierSubtask",
                    "enter_text": {"text": self._screenname, "link": "next_link"},
                }
            ],
        }

        self.enter_password_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:6",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginEnterPassword",
                    "enter_password": {"password": self._password, "link": "next_link"},
                }
            ],
        }
        self.acid_payload = {
            "subtask_inputs": [
                {
                    "subtask_id": "LoginAcid",
                    "enter_text": {"text": "", "link": "next_link"},
                }
            ],
        }

        # may be useful in the future if the mapping if subject to change
        self.tasks = {
            0: {"name": "LoginJsInstrumentationSubtask", "payload": self.get_sso_payload},
            1: {"name": "LoginEnterUserIdentifierSSO", "payload": self.enter_email_payload},
            5: {"name": "LoginEnterAlternateIdentifierSubtask", "payload": self.enter_alternative_id_payload},
            6: {"name": "LoginEnterPassword", "payload": self.enter_password_payload},
            7: {"name": "AccountDuplicationCheck", "payload": self.account_duplication_check_payload},
            8: {"name": "LoginAcid", "payload": self.acid_payload},
            13: {"name": "LoginSuccessSubtask", "payload": self.get_full_ct0_payload},
        }

    def _customize_headers(self, case):
        if case == "get_js":
            self._headers["Sec-Fetch-Mode"] = "no-cors"
            self._headers["Sec-Fetch-Dest"] = "script"
            self._headers["Referer"] = "https://twitter.com/i/flow/login"
            self._headers["Host"] = "twitter.com"
            del self._headers["Origin"]

        if case == "get_sso":
            self._headers["Sec-Fetch-Mode"] = "cors"
            self._headers["Sec-Fetch-Dest"] = "empty"
            self._headers["Referer"] = "https://twitter.com/"
            self._headers["Host"] = "api.twitter.com"
            self._headers["Origin"] = "https://twitter.com"
            self._headers["Content-Type"] = "application/json"

    def save_cookies_netscape_txt(self, cookie_path):
        with open(cookie_path, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for x in self._session.cookies:
                # DOMAIN(str) SUBDOMAIN?(bool) path(str) secure(bool) expire(int) name value
                f.write(f".twitter.com\tTRUE\t{x.path}\t{str(x.secure).upper()}\t2147483647\t{x.name}\t{x.value}\n")

    def save_cookies(self):
        # convert the cookiejar object to a dictionary; among duplicated entries, only the latest entry is kept
        cookie_dict = requests.utils.dict_from_cookiejar(self._session.cookies)
        # convert the dictionary back to a cookiejar object
        unique_cookiejar = requests.utils.cookiejar_from_dict(cookie_dict)
        self._session.cookies = unique_cookiejar

        if self._cookie_path.endswith(".txt"):
            self.save_cookies_netscape_txt(self._cookie_path)
            logger.info("cookies from requests saved as netscape txt file")
        else:
            # make it compatible with selenium cookie
            full_cookie = [
                {
                    "name": x.name,
                    "value": x.value,
                    "secure": x.secure,
                    "domain": ".twitter.com",
                    "path": x.path,
                }
                for x in self._session.cookies
            ]

            pickle.dump(full_cookie, open(self._cookie_path, "wb"))
            logger.info("cookies from requests saved as pickle file")

    def _prepare_next_login_task(self, r):
        logger.info(r.status_code)
        logger.debug(f"_prepare_next_login_task: {r.text}")
        j = r.json()
        self.login_flow_token = j["flow_token"]
        subtasks = j["subtasks"]

        logger.debug(f"flow_token: {self.login_flow_token}")

        for s in subtasks:
            logger.debug(f"{s['subtask_id']}")

    def _do_task(self):
        task = int(self.login_flow_token.split(":")[-1])
        logger.debug(self.tasks[task]["name"])

        # establish session and prepare for enter email
        if task == 0:
            self._customize_headers("get_js")
            r = self._session.get("https://twitter.com/i/js_inst?c_name=ui_metrics", headers=self._headers)

            # should have _twitter_sess cookie now
            # display_session_cookies(self._session)

            match = re.search(r"{'rf':{'.+};};", r.text)
            m = match.group(0)

            matches = re.finditer(r":([a-f0-9]{64})", m)
            for match in matches:
                found_string = match.group(1)
                new_string = ":" + str(int(random.uniform(-50, 200)))
                m = m.replace(":" + found_string, new_string)

            # get rid of ending ;};
            m = m[:-3]
            double_quoted_m = m.replace("'", '"')
            self.get_sso_payload["subtask_inputs"][0]["js_instrumentation"]["response"] = double_quoted_m

            self._customize_headers("get_sso")
            self.get_sso_payload["flow_token"] = self.login_flow_token

            # r = self._session.post(
            #    "https://api.twitter.com/1.1/onboarding/task.json",
            #    headers=self._headers,
            #    data=json.dumps(self.get_sso_payload),
            # )
            r = urllib_post("https://api.twitter.com/1.1/onboarding/task.json", headers=self._headers, payload=self.get_sso_payload, session=self._session)

        else:
            payload = self.tasks[task]["payload"]

            payload["flow_token"] = self.login_flow_token
            if task == 8:
                payload["subtask_inputs"][0]["enter_text"]["text"] = input(f"Enter Twitter Confirmation Code sent to {self._email}")

            # r = self._session.post(
            #    "https://api.twitter.com/1.1/onboarding/task.json",
            #    headers=self._headers,
            #    data=json.dumps(payload),
            # )
            r = urllib_post("https://api.twitter.com/1.1/onboarding/task.json", headers=self._headers, payload=payload, session=self._session)

        self._prepare_next_login_task(r)

    def get_login_flow_token(self):
        r = self._session.get("https://twitter.com/i/flow/login")

        try:
            # the gt value is not directly visible in the returned cookies; it's hidden in the returned html file's script
            match = re.search(
                r'document\.cookie = decodeURIComponent\("gt=(\d+); Max-Age=10800; Domain=\.twitter\.com; Path=/; Secure"\);',
                r.text,
            )
            self._session.cookies.set("gt", match.group(1))
            self._headers["x-guest-token"] = str(self._session.cookies.get("gt"))

        except:
            logger.debug("cannot find guest token from the webpage")
            r = self._session.post("https://api.twitter.com/1.1/guest/activate.json", data=b"", headers=self._headers)

            if r.status_code == 200:
                self._headers["x-guest-token"] = r.json()["guest_token"]
                self._session.cookies.set("gt", self._headers["x-guest-token"])
                logger.debug("got guest token from the endpoint")

        # the ct0 value is just a random 32-character string generated from random bytes at client side
        self._session.cookies.set("ct0", genct0())

        # set the headers accordingly
        self._headers["x-csrf-token"] = self._session.cookies.get("ct0")

        # r = self._session.post(
        #    "https://api.twitter.com/1.1/onboarding/task.json?flow_name=login",
        #    headers=self._headers,
        #    params=self.get_token_payload,
        # )
        url = "https://api.twitter.com/1.1/onboarding/task.json?flow_name=login"
        r = urllib_post(url, headers=self._headers, payload=self.get_token_payload, session=self._session)

        self._prepare_next_login_task(r)
        # att is set by the response cookie


class TwitterBot:
    tmp_count = 0

    badge_form = {"supports_ntab_urt": "1"}

    notification_all_form = {
        "include_profile_interstitial_type": "1",
        "include_blocking": "1",
        "include_blocked_by": "1",
        "include_followed_by": "1",
        "include_want_retweets": "1",
        "include_mute_edge": "1",
        "include_can_dm": "1",
        "include_can_media_tag": "1",
        "include_ext_has_nft_avatar": "1",
        "include_ext_is_blue_verified": "1",
        "include_ext_verified_type": "1",
        "skip_status": "1",
        "cards_platform": "Web-12",
        "include_cards": "1",
        "include_ext_alt_text": "true",
        "include_ext_limited_action_results": "false",
        "include_quote_count": "true",
        "include_reply_count": "1",
        "tweet_mode": "extended",
        "include_ext_views": "true",
        "include_entities": "true",
        "include_user_entities": "true",
        "include_ext_media_color": "true",
        "include_ext_media_availability": "true",
        "include_ext_sensitive_media_warning": "true",
        "include_ext_trusted_friends_metadata": "true",
        "send_error_codes": "true",
        "simple_quoted_tweet": "true",
        "count": "40",
        # "cursor": "DAABDAABCgABAAAAABZfed0IAAIAAAABCAADYinMQAgABFMKJicACwACAAAAC0FZWlhveW1SNnNFCAADjyMIvwAA",
        "ext": "mediaStats,highlightedLabel,hasNftAvatar,voiceInfo,birdwatchPivot,enrichments,superFollowMetadata,unmentionInfo,editControl,vibe",
    }

    adaptive_search_form = copy.deepcopy(notification_all_form)
    adaptive_search_form["tweet_search_mode"] = "live"
    adaptive_search_form["query_source"] = "typed_query"
    adaptive_search_form["include_ext_edit_control"] = "true"
    adaptive_search_form["spelling_corrections"] = "1"
    adaptive_search_form["pc"] = "1"

    standard_graphql_features = {
        "responsive_web_twitter_blue_verified_badge_is_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": False,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "tweetypie_unmention_optimization_enabled": True,
        "vibe_api_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": False,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
        "interactive_text_enabled": True,
        "responsive_web_text_conversations_enabled": False,
        "longform_notetweets_richtext_consumption_enabled": False,
        "responsive_web_enhance_cards_enabled": False,
        "rweb_lists_timeline_redesign_enabled": True,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
    }

    combined_lists_form = {
        "variables": {"userId": "86539341", "count": 100},
        "features": standard_graphql_features,
    }

    tweet_detail_form = {
        "variables": {
            "focalTweetId": "1645587845359468551",
            # "cursor": "NAEAAPAOHBn2IYDA0a2avq3WLYLA0ZnX8tjWLYCA0dGl664SAOHU4cC4sdYtgMDRgdCXrCQA0LW-7a3WLYyA06nn59ItAPAb0tWD1K7WLYiA0LGuv9bXLYLA0LGpxNbXLYyAtsGA0r-0LYCAvumX5fzXWgBAreXRsUgAUNPZgrGsWgBR0Pm3xNEJANDhpoOg2C2EwNTty-LiLQBQ1IXzgq4bAODUvbrLx9cthsDT7diluhIAUdLl5JnZCQBBkdTmp7QAMd2r4qIAUNKRwN7TCQDwB9DpxPLT1i2EwNPdmJ_Z1y2AwNPR8MkkAPABgNOhj_781i2-gL3F3ZzZo2MAMaW5kJkAUdClkaP9kADwB_GfvKzWLYzA0-m5htPWLSUCEhUEAAA",
            "referrer": "tweet",
            "with_rux_injections": False,
            "includePromotedContent": True,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withDownvotePerspective": False,
            "withVoice": True,
            "withV2Timeline": True,
        },
        "features": standard_graphql_features,
    }

    create_tweet_form = {
        "variables": {
            "tweet_text": "test",
            "dark_request": False,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False,
            },
            "withDownvotePerspective": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "semantic_annotation_ids": [],
        },
        "features": standard_graphql_features,
    }

    following_followers_form = {
        "variables": {
            "userId": None,
            "count": 100,
            "includePromotedContent": False,
            "withSuperFollowsUserFields": True,
            "withDownvotePerspective": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "withSuperFollowsTweetFields": True,
        },
        "features": standard_graphql_features,
    }

    tweet_replies_form = {
        "variables": {
            "userId": "1629601029678309376",
            "count": 100,
            # "cursor": "HCaAgICU9oDCqS0AAA==",
            "includePromotedContent": True,
            "withCommunity": True,
            # "withSuperFollowsUserFields": True,
            # "withDownvotePerspective": False,
            # "withReactionsMetadata": False,
            # "withReactionsPerspective": False,
            # "withSuperFollowsTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        },
        "features": standard_graphql_features,
        "fieldToggles": {"withArticleRichContentState": False},
    }

    blocklist_form = {
        "variables": {"count": 20, "includePromotedContent": False, "withSafetyModeUserFields": False},
        "features": standard_graphql_features,
        "fieldToggles": {"withAuxiliaryUserLabels": False, "withArticleRichContentState": False},
    }

    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,zh-CN;q=0.7,zh;q=0.6,zh-TW;q=0.5,ja;q=0.4,es;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Host": "api.twitter.com",
        "Referer": "https://twitter.com/",
        "x-twitter-polling": "true",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
        "x-csrf-token": "1fda97d345e0c46c2eb430eee5d916b3a4cb129ae6bb97f54a8bc279bff5b33b26a11ce36075550e911797aae312bb47365aa41ed205717c262310bcfd94746bca374a1c7f45ed0a214a389478d9590b",
        "Origin": "https://twitter.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        # "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        # "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAAPYXBAAAAAAACLXUNDekMxqa8h%2F40K4moUkGsoc%3DTYfbDKbT3jJPCEVnMYqilB28NHfOPqkca3qaAxGfsyKCs0wRbw",
        "Connection": "keep-alive",
        "TE": "trailers",
    }

    def __init__(self, cookie_path=None, config_path=None, white_list_path=None, block_list_path=None, backup_log_path=None):
        """
        In order to save the list of newly blocked accounts, the block_list_path should be specified, even if you have not created that file.

        Parameters:
        cookie_path (str): the path of a python pickle file or a Netscape HTTP Cookie File in txt format of the requests session cookie. (mandatory)
        config_path (str): the path of the config file which contains login info and the filter setting. (optional)
        white_list_path (str): the path of the white list yaml file. (optional)
        block_list_path (str): the path of the black list yaml file. (optional) when not provided, the blocked id will not be saved.
        backup_log_path (str): the path to the notification log file. (optional) when not provided, the parsed interactions from notifications will not be saved.
        """
        self._headers = copy.deepcopy(TwitterBot.default_headers)

        self._session = Session()

        self._cookie_path = cookie_path

        if config_path is not None:
            self._config_path = config_path
            self._config_dict = load_yaml(config_path)
        else:
            self._config_dict = dict()

        if block_list_path is not None:
            self._block_list_path = block_list_path
            self._block_list = load_yaml(self._block_list_path)
        else:
            self._block_list = dict()

        if white_list_path is not None:
            self._white_list_path = white_list_path
            self._white_list = load_yaml(self._white_list_path)
        else:
            self._white_list = dict()

        if "filtering_rule" in self._config_dict:
            self._filtering_rule = self._config_dict["filtering_rule"]
        else:
            self._filtering_rule = "(followers_count < 5) or (days < 180)"

        self._backup_log_path = backup_log_path

        try:
            self._load_cookies()
        except:
            # if the cookie does not exist
            traceback.print_exc()
            self.refresh_cookies()

        # display_session_cookies(self._session)

        # when disabled, will use the default cursor
        if "latest_cursor" in self._config_dict:
            self._load_cursor()

        self._select_search_method()

        # self.reporter = ReportHandler(self._headers, self._session)

    def _set_selenium_cookies(self, cookies):
        logger.debug("setting cookies")
        for x in cookies:
            logger.debug(f"{x}")
            otherinfo = dict()
            if "secure" in x:
                otherinfo = {
                    "secure": x["secure"],
                    "domain": x["domain"],
                    "path": x["path"],
                }

            if "expiry" in x:
                otherinfo["expires"] = x["expiry"]
            self._session.cookies.set(x["name"], x["value"], **otherinfo)
        # make the header token consistent with the cookies
        self._headers["x-csrf-token"] = self._session.cookies.get("ct0")

    def _load_cookies(self):
        if self._cookie_path.endswith(".pkl"):
            logger.debug("loading cookies")
            cookies = pickle.load(open(self._cookie_path, "rb"))
            self._set_selenium_cookies(cookies)
        elif self._cookie_path.endswith(".txt"):
            self.set_cookies_from_netscape_txt(self._cookie_path)
        # g_state is not necessary

    def set_cookies_from_netscape_txt(self, cookie_path):
        cj = http.cookiejar.MozillaCookieJar(cookie_path)
        cj.load()
        self._session.cookies.update(cj)
        self._headers["x-csrf-token"] = self._session.cookies.get("ct0")

    def refresh_cookies(self):
        """
        Try to get the cookies through requests only TwitterLoginBot first.
        If it does not work, use SeleniumTwitterBot to get the cookies
        """
        try:
            logger.info("trying using requests to get cookies")
            if "phonenumber" in self._config_dict["login"]:
                phonenumber = self._config_dict["login"]["phonenumber"]
            else:
                phonenumber = None
            b = TwitterLoginBot(
                self._config_dict["login"]["email"],
                self._config_dict["login"]["password"],
                self._config_dict["login"]["screenname"],
                phonenumber=phonenumber,
                cookie_path=self._cookie_path,
            )
            self._load_cookies()
        except:
            logger.info("trying using selenium to get cookies")
            b = SeleniumTwitterBot(config_path=self._config_path, cookie_path=self._cookie_path)
            # new cookie will be saved from selenium
            b.twitter_login()
            b.save_cookies()

            self._set_selenium_cookies(b.driver.get_cookies())

    def _select_search_method(self):
        self.search_timeline = self.search_timeline_graphql
        return
        try:
            for x in self.search_timeline_graphql("world", batch_count=20):
                tmp = x.user
                self.search_timeline = self.search_timeline_graphql
                logger.info("graphql search selected")
                break
        except:
            self.search_timeline = self.search_timeline_login_legacy
            logger.info("legacy search selected")

    def get_badge_count(self):
        # display_session_cookies(self._session)
        url = "https://api.twitter.com/2/badge_count/badge_count.json"
        badge_form = TwitterBot.badge_form
        r = self._session.get(url, headers=self._headers, params=badge_form)

        if r.status_code == 200:
            result = r.json()
            return r.status_code, result

    def update_local_cursor(self, val):
        TwitterBot.notification_all_form["cursor"] = val
        self._config_dict["latest_cursor"] = val

        if hasattr(self, "_config_path") and self._config_path is not None:
            save_yaml(self._config_dict, self._config_path, "w")

    def _load_cursor(self):
        if len(self._config_dict["latest_cursor"].strip()) > 0:
            TwitterBot.notification_all_form["cursor"] = self._config_dict["latest_cursor"]
        logger.info(f"after loading cursor:{TwitterBot.notification_all_form['cursor']}")

    def update_remote_cursor(self, val):
        url = "https://api.twitter.com/2/notifications/all/last_seen_cursor.json"
        cursor_form = {"cursor": val}
        r = self._session.post(url, headers=self._headers, params=cursor_form)

        if r.status_code == 200:
            logger.info(f"remote cursor updated to {val}")

    def update_remote_latest_cursor(self):
        """
        Updates the top cursor value in the API, using self.latest_cursor.

        This function does not take any arguments and does not return a value.

        The badge will disappear after you refresh in a non-notification page
        """

        self.update_remote_cursor(TwitterBot.notification_all_form["cursor"])

    def block_user(self, user_id):
        user_id = self.numerical_id(user_id)

        url = "https://api.twitter.com/1.1/blocks/create.json"
        block_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=block_form)

        if r.status_code == 200:
            logger.info(f"block {user_id}: successfully sent block post!")
            response = r.json()
                # update the block list
            if hasattr(self, "_block_list_path"):
                self._block_list[user_id] = response["screen_name"]
                save_yaml(self._block_list, self._block_list_path, "w")

    def unblock_user(self, user_id):
        user_id = self.numerical_id(user_id)

        url = "https://api.twitter.com/1.1/blocks/destroy.json"
        unblock_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=unblock_form)

        if r.status_code == 200:
            logger.info(f"unbock {user_id}: successfully sent unblock post!")

    def mute_user(self, user_id):
        user_id = self.numerical_id(user_id)

        url = "https://api.twitter.com/1.1/mutes/users/create.json"
        mute_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=mute_form)

        if r.status_code == 200:
            logger.info(f"mute {user_id}: successfully sent mute post!")

    def unmute_user(self, user_id):
        user_id = self.numerical_id(user_id)

        url = "https://api.twitter.com/1.1/mutes/users/destroy.json"
        unmute_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=unmute_form)

        if r.status_code == 200:
            logger.info(f"unmute {user_id}: successfully sent unmute post!")

    def judge_users(self, users, block=False):
        """
        Examine users coming from the notifications one by one.
        Block bad users. Update the local block list.
        """

        # ignore user already in block_list or white_list
        sorted_users = {user_id: users[user_id] for user_id in users if (user_id not in self._block_list) and (user_id not in self._white_list)}
        users_judgements = dict()

        for user_id in sorted_users:
            user = sorted_users[user_id]

            is_bad = oracle(user, self._filtering_rule)

            conclusion_str = "bad" if is_bad else "good"

            if is_bad and block:
                self.block_user(user_id)

                self._block_list[user.user_id] = user.screen_name
                save_yaml(self._block_list, self._block_list_path, "w")

            logger.info(
                f"ORACLE TIME!: id {user.user_id:<25} name {user.screen_name:<16} followers_count {user.followers_count:<10} days_since_reg {user.days_since_registration:<5} is {conclusion_str}"
            )
            users_judgements[user_id] = conclusion_str
        return users_judgements

    def get_interactions_from_notifications(self, update_remote_cursor=False):
        url = "https://api.twitter.com/2/notifications/all.json"
        notification_all_form = TwitterBot.notification_all_form
        r = self._session.get(url, headers=self._headers, params=notification_all_form)

        logger.info("notifications/all.json")
        logger.debug(f"status_code: {r.status_code}, length: {r.headers['content-length']}")

        result = r.json()
        logger.debug(f"{result}")
        result = TwitterJSON(result)

        logger.debug(f"result keys: {result.keys()}")

        convo = set()
        tweets, notifications = [], []

        logger.debug(f"globalObjects keys: {result.globalObjects.keys()}")

        logged_users = {}

        if result.globalObjects.users:
            users = result.globalObjects.users
            # annoying: cannot use variable in dot attribute getter
            for user in users.values():
                p = TwitterUserProfile(
                    user.id,
                    user.screen_name,
                    created_at=sns_timestamp_from_tweet_timestamp(user.created_at),
                    following_count=user.friends_count,
                    followers_count=user.followers_count,
                    tweet_count=user.statuses_count,
                    media_count=user.media_count,
                    favourites_count=user.favourites_count,
                    display_name=user.name,
                )
                logged_users[p.user_id] = p

        # display_msg("globalObjects['tweets]")
        id_indexed_tweets = {}
        # all related tweets (being liked; being replied to; being quoted; other people's interaction with me)
        if result.globalObjects.tweets:
            tweets = result.globalObjects.tweets
            for tweet in tweets.values():
                id_indexed_tweets[int(tweet.id)] = tweet
                # print("convo id:", tweet.conversation_id)
                convo.add(tweet.conversation_id)
                # print(tweet.user_id, tweet.created_at, tweet.full_text)

        interacting_users = {}
        notification_id_to_user_id = {}

        if result.globalObjects.notifications:
            notifications = result.globalObjects.notifications
            # userid and sortindex available; but not interaction type
            for notification in notifications.values():
                print(notification)
                # print(notification.message.text)
                notification_id_to_user_id[notification.id] = []
                for e in notification.message.entities:
                    # there might be notifications that have non-empty entities field but do not contain any user
                    if e.ref:
                        if e.ref.user:
                            entry_user_id = int(e.ref.user.id)
                            # add the users appearing in notifications (do not include replies)
                            notification_id_to_user_id[notification.id].append(entry_user_id)

        logger.info(f"TIMELINE ID: {result.timeline.id}")
        instructions = result.timeline.instructions  # instructions is a list

        # print all keys
        # print("instruction keys:", [x.keys() for x in instructions])

        # get entries
        for instruction in instructions:
            if instruction.addEntries:
                entries = instruction.addEntries.entries  # intries is a list

        # get cursor entries
        cursor_entries = [x for x in entries if x.content.operation]
        # entries that are not cursors
        non_cursor_entries = [x for x in entries if not x.content.operation]

        # includes like, retweet, other misc
        non_cursor_notification_entries = [x for x in non_cursor_entries if x.content.item.content.notification]
        # includes reply, quoted retweet
        non_cursor_tweet_entries = [x for x in non_cursor_entries if x.content.item.content.tweet]

        # users_liked_your_tweet/user_liked_multiple_tweets/user_liked_tweets_about_you/generic_login_notification/generic_report_received/users_retweeted_your_tweet ; no userid is included in these entries
        for entry in non_cursor_notification_entries:
            if entry.content.item.clientEventInfo.element not in [
                "generic_login_notification",
                "generic_report_received",
                "generic_abuse_report_actioned_with_count",
                "generic_magic_rec_first_degree_tweet_recent",
                "generic_magic_fanout_creator_subscription",
            ]:
                entry_id = entry.entryId[13:]
                entry_user_ids = notification_id_to_user_id[entry_id]
                for entry_user_id in entry_user_ids:
                    logger.info(f"timeline_non_cursor_notification {entry.sortIndex} {entry.content.item.clientEventInfo.element} {entry_user_id}")
                    expanded_entry_id = str(entry_id) + "_" + str(entry_user_id)
                    interacting_users[expanded_entry_id] = {
                        "sort_index": entry.sortIndex,
                        "user_id": entry_user_id,
                        "user": logged_users[entry_user_id],
                        "event_type": entry.content.item.clientEventInfo.element,
                    }

        # user_replied_to_your_tweet/user_quoted_your_tweet
        for entry in non_cursor_tweet_entries:
            entry_id = entry.entryId[13:]
            entry_user_id = id_indexed_tweets[int(entry.content.item.content.tweet.id)].user_id
            logger.info(f"timeline_non_cursor_tweets {entry.sortIndex} {entry.content.item.clientEventInfo.element} {entry_user_id}")
            # add the users replying to me
            interacting_users[entry_id] = {
                "sort_index": entry.sortIndex,
                "user_id": entry_user_id,
                "user": logged_users[entry_user_id],
                "event_type": entry.content.item.clientEventInfo.element,
            }

        # sort by time from latest to earliest
        for x in sorted(interacting_users.items(), key=lambda item: item[1]["sort_index"], reverse=True):
            logger.info(f"all_interactions {x[1]['user'].screen_name:<16} {x[1]['event_type']}")

        """
        print("\ntweets VS non_cursor_entries", len(tweets), len(non_cursor_entries))
        print(
            "notifications VS non_cursor_notification",
            len(notifications),
            len(non_cursor_notification_entries),
        )
        print("number of convos", len(convo))
        """
        for entry in cursor_entries:
            cursor = entry.content.operation.cursor
            logger.debug(f"cursors: {entry.sortIndex} {cursor}")
            if cursor.cursorType == "Top":
                self.latest_sortindex = entry.sortIndex

                self.update_local_cursor(cursor.value)
                if update_remote_cursor:
                    self.update_remote_latest_cursor()  # will cause the badge to disappear
        return interacting_users

    def check_notifications(self, block=True, update_remote_cursor=False):
        """
        Gets the recent notifications from the endpoint.

        Whenever there is new notification, or you perform operations like block/unblock, mute/unmute, you will get new stuff here.

        Updates latest_cursor using the top cursor fetched. After the update, if no new thing happens, then you will not get anything here.

        Block bad users.

        """
        interacting_users = self.get_interactions_from_notifications(update_remote_cursor=update_remote_cursor)

        users_judgements = self.judge_users(
            {interacting_users[entry_id]["user_id"]: interacting_users[entry_id]["user"] for entry_id in interacting_users}, block=block
        )

        backup_events = dict()
        if self._backup_log_path is not None:
            for entry_id in interacting_users:
                # print(interacting_users[entry_id])
                event_time = (
                    datetime.utcfromtimestamp(int(interacting_users[entry_id]["sort_index"]) // 1000).replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                )
                user_dict = dtc_asdict(interacting_users[entry_id]["user"])
                if event_time not in backup_events:
                    backup_events[event_time] = []
                backup_events[event_time].append(
                    {
                        "user": {key: value for (key, value) in user_dict.items() if value is not None},
                        "event_type": interacting_users[entry_id]["event_type"],
                    }
                )
            if len(backup_events) > 0:
                save_yaml(backup_events, self._backup_log_path, "a")

    @staticmethod
    def _cursor_from_entries(entries):
        for e in entries[-2:]:
            content = e.content
            if content.entryType == "TimelineTimelineCursor":
                if content.cursorType == "Bottom":
                    return content.value
            elif content.entryType == "TimelineTimelineItem":
                if (
                    content.itemContent.cursorType == "Bottom"
                    or content.itemContent.cursorType == "ShowMoreThreads"
                    or content.itemContent.cursorType == "ShowMoreThreadsPrompt"
                ):
                    return content.itemContent.value

    @staticmethod
    def _status_and_user_from_result(result):
        """
        Extract the user profile from the result dictionary.
        """
        # non-normal result could happen when the result is fetched from the user related endpoints
        # impossible when the result is embedded in other returned entries
        if not result:  # cannot use is None here because None is wrapped in TwitterJSON
            return "does_not_exist", None

        user = result.legacy

        if result.__typename == "User":
            p = TwitterUserProfile(
                int(result.rest_id),
                user.screen_name,
                created_at=sns_timestamp_from_tweet_timestamp(user.created_at),
                following_count=user.friends_count,
                followers_count=user.followers_count,
                tweet_count=user.statuses_count,
                media_count=user.media_count,
                favourites_count=user.favourites_count,
                display_name=user.name,
                blocked=user.blocking,
            )
            if result.legacy.profile_interstitial_type == "fake_account":
                return "fake_account", p
            if result.legacy.protected:
                return "protected", p
            return "normal", p

        if result.__typename == "UserUnavailable":
            if not result.message and result.reason == "NoReason":
                return "unavailable_for_no_reason", None
            if "suspend" in result.message:
                return "suspended", None

    @staticmethod
    def _users_from_entries(entries):
        for e in entries:
            content = e.content
            if content.entryType == "TimelineTimelineItem":
                r = content.itemContent.user_results.result
                status, user = TwitterBot._status_and_user_from_result(r)

                if user is not None:
                    yield user
                else:
                    logger.info(f"cannot get user data: {e.entryId}")

    @staticmethod
    def _tweet_type(tweet):
        # a retweet could be anything, but it's a retweet first.
        if "RT @" in tweet.full_text:
            return "retweeted"
        if tweet.in_reply_to_status_id_str:
            if tweet.is_quote_status:
                return "reply_by_quote"
            return "reply"
        else:
            if tweet.is_quote_status:
                return "quote"
            return "original"

    @staticmethod
    def _cdn_tweet_type(info):
        if "retweeted_tweet_id" in info:
            return "retweeted"
        if "replied_tweet_id" in info:
            if "quoted_tweet_id" in info:
                return "reply_by_quote"
            return "reply"
        else:
            if "quoted_tweet_id" in info:
                return "quote"
            return "original"

    @staticmethod
    def _tweet_from_result(result):
        if not result:
            #to handle the deleted tweet case for tweet_by_rest_id
            return
        try:
            tweet_type = TwitterBot._tweet_type(result.legacy)
            _, user = TwitterBot._status_and_user_from_result(result.core.user_results.result)
        except:
            logger.debug(f"{result}")
            return

        # None by default
        quoted_tweet_id, quoted_user_id = None, None
        replied_tweet_id, replied_user_id = None, None
        retweeted_tweet_id, retweeted_user_id = None, None

        if tweet_type == "quote" or tweet_type == "reply_by_quote":
            try:
                quoted_tweet_id = int(result.legacy.quoted_status_id_str)
                # could be tombstone
                if result.quoted_status_result.result.legacy:
                    quoted_user_id = int(result.quoted_status_result.result.legacy.user_id_str)
            except:
                logger.debug(f"quote: {result}")

        if tweet_type == "reply" or tweet_type == "reply_by_quote":
            try:
                replied_tweet_id = int(result.legacy.in_reply_to_status_id_str)
                replied_user_id = int(result.legacy.in_reply_to_user_id_str)
            except:
                logger.debug(f"reply: {result}")

        if tweet_type == "retweeted":
            try:
                retweeted_tweet_id = int(result.legacy.retweeted_status_result.result.rest_id)
                retweeted_user_id = int(result.legacy.retweeted_status_result.result.legacy.user_id_str)
            except:
                logger.debug(f"retweet: {result}")

        media = []
        if result.legacy.extended_entities:
            for m in result.legacy.extended_entities.media:
                media_type = m.type
                if media_type == "photo":
                    url = m.media_url_https
                elif media_type == "video" or media_type == "animated_gif":
                    variants = m.video_info.variants
                    highest_bitrate_variant_url = max(variants, key=lambda x: x.get("bitrate", 0))["url"]
                    url = highest_bitrate_variant_url.split("?")[0].strip()
                media.append({"type": media_type, "url": url})

        tweet = Tweet(
            int(result.rest_id),
            tweet_type=tweet_type,
            quoted_tweet_id=quoted_tweet_id,
            quoted_user_id=quoted_user_id,
            replied_tweet_id=replied_tweet_id,
            replied_user_id=replied_user_id,
            retweeted_tweet_id=retweeted_tweet_id,
            retweeted_user_id=retweeted_user_id,
            created_at=sns_timestamp_from_tweet_timestamp(result.legacy.created_at),
            source=result.source,
            text=result.legacy.full_text,
            lang=result.legacy.lang,
            view_count=result.views.count,
            favorite_count=result.legacy.favorite_count,
            reply_count=result.legacy.reply_count,
            retweet_count=result.legacy.retweet_count,
            quote_count=result.legacy.quote_count,
            bookmark_count=result.legacy.bookmark_count,
            hashtags=[x["text"] for x in result.legacy.entities.hashtags],
            media=media,
            user_mentions=[TwitterUserProfile(int(x.id_str), x.screen_name) for x in result.legacy.entities.user_mentions],
            user=user,
        )
        return tweet

    @staticmethod
    def _yield_tweet_from_result(result):
        #a wrapper to facilitate the use of yield from so that non-yielded ones are ignored automatically without having to check None
        tweet = TwitterBot._tweet_from_result(result)
        if not tweet:
            return
        # TODO: might be redundant if  promoted-tweet is already filtered at entryId in _text_from_entries
        if not (("advertiser-interface" in tweet.source) or ("Twitter for Advertisers" in tweet.source)):
            yield tweet

    @staticmethod
    def _list_from_list(listdict):
        status, user = TwitterBot._status_and_user_from_result(listdict.user_results.result)
        twitter_list = TwitterList(
            int(listdict.id_str),
            name=listdict.name,
            description=listdict.description,
            member_count=listdict.member_count,
            subscriber_count=listdict.subscriber_count,
            user=user,
        )
        return twitter_list

    @staticmethod
    def _text_from_entries(entries, user_id=None):
        for e in entries:
            if "promoted-tweet" in e.entryId:
                continue
            content = e.content
            if content.entryType == "TimelineTimelineModule":
                for i in content.items:
                    itemContent = i.item.itemContent
                    if itemContent.__typename == "TimelineTweet":
                        result = itemContent.tweet_results.result  # could be None
                        if result.__typename == "Tweet":
                            # when user_id is not provided, return everything; otherwise only return tweets from user_id
                            if user_id is None or int(result.core.user_results.result.rest_id) == user_id:
                                yield from TwitterBot._yield_tweet_from_result(result)
                        elif result.__typename == "TweetWithVisibilityResults":
                            yield from TwitterBot._yield_tweet_from_result(result.tweet)
            elif content.entryType == "TimelineTimelineItem":
                itemContent = content.itemContent
                if itemContent.__typename == "TimelineTweet":
                    result = itemContent.tweet_results.result  # could be None
                    if result.__typename == "Tweet":
                        yield from TwitterBot._yield_tweet_from_result(result)
                    elif result.__typename == "TweetWithVisibilityResults":
                        yield from TwitterBot._yield_tweet_from_result(result.tweet)
                elif itemContent.__typename == "TimelineTwitterList":
                    twitter_list = itemContent.list
                    yield TwitterBot._list_from_list(twitter_list)

    def _json_headers(self):
        headers = copy.deepcopy(self._headers)
        headers["Content-Type"] = "application/json"
        headers["Host"] = "twitter.com"

        return headers

    @staticmethod
    def _navigate_graphql_entries(session_type, url, form, session=None, headers=None):
        while True:
            encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})
            # generate session and header for guest mode
            if session_type != SessionType.Authenticated:
                session, headers = TwitterBot.tmp_session_headers()
            r = session.get(url, headers=headers, params=encoded_params)
            if r.status_code != 200:
                logger.debug(f"{r.request.url}")
                logger.debug(f"{headers}")
                break

            response = r.json()
            response = TwitterJSON(response)

            data = response.data
            if len(data) == 0:
                return

            if data.retweeters_timeline:
                instructions = data.retweeters_timeline.timeline.instructions
            elif data.threaded_conversation_with_injections_v2:
                instructions = data.threaded_conversation_with_injections_v2.instructions
            elif data.search_by_raw_query:
                instructions = data.search_by_raw_query.search_timeline.timeline.instructions
            elif data.viewer.timeline:
                instructions = data.viewer.timeline.timeline.instructions  # blocklist
            elif data.viewer.muting_timeline:
                instructions = data.viewer.muting_timeline.timeline.instructions  # mutelist
            else:
                result = data.user.result
                if result.timeline_v2:
                    instructions = result.timeline_v2.timeline.instructions
                elif result.timeline:
                    instructions = result.timeline.timeline.instructions
                else:
                    return

            add_instructions = [x for x in instructions if x.type == "TimelineAddEntries"]
            if len(add_instructions) != 0:
                entries = add_instructions[0].entries
            else:
                entries = []
            entries += [x.entry for x in instructions if x.type == "TimelineReplaceEntry"]

            yield entries

            if len(entries) <= 2:
                break

            bottom_cursor = TwitterBot._cursor_from_entries(entries)
            # could happen when nagivating tweet threads
            if not bottom_cursor:
                break
            form["variables"]["cursor"] = bottom_cursor

    #@staticmethod
    def get_user_lists(self, user_id):
        """
        Get a user's lists.
        """
        user_id = self.numerical_id(user_id)

        url = "https://twitter.com/i/api/graphql/rIxum3avpCu7APi7mxTNjw/CombinedLists"
        # tmp_session, tmp_headers = TwitterBot.tmp_session_headers()
        headers = self._json_headers()

        form = copy.deepcopy(TwitterBot.combined_lists_form)
        form["variables"]["userId"] = str(user_id)
        form["features"]["blue_business_profile_image_shape_enabled"] = True
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True

        #for entries in TwitterBot._navigate_graphql_entries(SessionType.Guest, url, form):
        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from TwitterBot._text_from_entries(entries, user_id=user_id)

    # @staticmethod
    # def get_tweets_replies(user_id):
    def get_tweets_replies(self, user_id, batch_count=100):
        """
        Gets the texts from the user's tweets and replies tab.
        """
        user_id = self.numerical_id(user_id)

        headers = self._json_headers()
        url = "https://twitter.com/i/api/graphql/ahLGvWSvDCr-57-E8GXGCQ/UserTweetsAndReplies"

        # tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"]["userId"] = str(user_id)
        form["variables"]["count"] = batch_count
        form["features"]["responsive_web_graphql_exclude_directive_enabled"] = True
        form["features"]["responsive_web_twitter_article_tweet_consumption_enabled"] = False
        form["features"]["tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled"] = True
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True

        # for entries in TwitterBot._navigate_graphql_entries(SessionType.Guest, url, form):
        #    yield from TwitterBot._text_from_entries(entries, user_id = user_id)
        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._text_from_entries(entries, user_id=user_id)

    def get_following(self, user_id, batch_count=100):
        """
        Gets the list of following.
        Returns a list of TwitterUserProfile.
        """
        user_id = self.numerical_id(user_id)

        headers = self._json_headers()

        url = "https://twitter.com/i/api/graphql/AmvGuDw_fxEbJtEXie4OkA/Following"

        form = copy.deepcopy(TwitterBot.following_followers_form)

        # set userID in form
        form["variables"]["userId"] = str(user_id)
        form["variables"]["count"] = batch_count

        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._users_from_entries(entries)

    def get_followers(self, user_id, batch_count=100):
        """
        Gets the list of followers.
        Returns a list of TwitterUserProfile.
        """
        user_id = self.numerical_id(user_id)

        headers = self._json_headers()

        url = "https://twitter.com/i/api/graphql/utPIvA97eaEvxfra_PQz_A/Followers"

        form = copy.deepcopy(TwitterBot.following_followers_form)
        form["variables"]["count"] = batch_count

        # set userID in form
        form["variables"]["userId"] = str(user_id)

        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._users_from_entries(entries)

    def get_retweeters(self, tweet_id, batch_count=100):
        """
        Gets the list of visible (not locked) retweeters.
        Returns a list of TwitterUserProfile.
        """
        # needs to have the br decoding library installed for requests to handle br compressed results

        headers = self._json_headers()

        url = "https://twitter.com/i/api/graphql/ViKvXirbgcKs6SfF5wZ30A/Retweeters"

        form = copy.deepcopy(TwitterBot.following_followers_form)
        del form["variables"]["userId"]
        # del form["features"]["longform_notetweets_richtext_consumption_enabled"]

        # set tweetId in form
        form["variables"]["tweetId"] = tweet_id
        form["variables"]["count"] = batch_count

        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._users_from_entries(entries)

    def delete_tweet(self, tweet_id):
        headers = self._json_headers()
        url = "https://twitter.com/i/api/graphql/VaenaVgh5q5ih7kvyVjgtg/DeleteTweet"
        form = {
            "variables": {
                "tweet_id": str(tweet_id),
                "dark_request": False,
            },
            "queryId": queryID_from_url(url),
        }
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            return response.data.delete_tweet.tweet_results

    def _tweet_creation_form(self, text, media_ids=None, conversation_control=None):
        form = copy.deepcopy(TwitterBot.create_tweet_form)
        form["variables"]["tweet_text"] = text

        if media_ids is not None:
            for media_id in media_ids:
                form["variables"]["media"]["media_entities"].append({"media_id": media_id, "tagged_users": []})
        if conversation_control is not None:
            form["variables"]["conversation_control"] = {"mode": conversation_control}

        form["features"]["view_counts_everywhere_api_enabled"] = False
        del form["features"]["responsive_web_twitter_blue_verified_badge_is_enabled"]
        form["features"]["blue_business_profile_image_shape_enabled"] = False
        form["features"]["responsive_web_graphql_exclude_directive_enabled"] = True

        return form

    def _reply_creation_form(self, tweet_id, text, media_ids=None):
        form = self._tweet_creation_form(text, media_ids=media_ids)
        form["variables"]["reply"] = {"in_reply_to_tweet_id": str(tweet_id), "exclude_reply_user_ids": []}
        form["variables"]["batch_compose"] = "BatchSubsequent"

        return form

    def _tweet_creation_headers(self):
        headers = self._json_headers()
        headers["Referer"] = "https://twitter.com/home"
        headers["Sec-Fetch-Site"] = "same-origin"
        del headers["x-twitter-polling"]

        return headers

    def _reply_creation_headers(self):
        headers = self._tweet_creation_headers()
        headers["Referer"] = "https://twitter.com/compose/tweet"
        return headers

    def _upload_image(self, path):
        # INIT: regular header
        headers = copy.deepcopy(self._headers)
        headers["Host"] = "upload.twitter.com"
        url = "https://upload.twitter.com/i/media/upload.json"
        try:
            with open(path, "rb") as f:
                binary_data = f.read()
            total_img_size = len(binary_data)
            # file too large!
            if total_img_size > 5242880:
                return None
            img_suffix = image_file_type(path).lower()
            upload_init_form = {
                "command": "INIT",
                "total_bytes": total_img_size,
                "media_type": f"image/{img_suffix}",
                "media_category": "tweet_image",
            }
            r = self._session.post(url, headers=headers, params=upload_init_form)
            response = r.json()
            media_id = response["media_id"]

            # APPEND
            chunksize = 2048000
            import math

            n_segments = math.ceil(total_img_size / chunksize)
            current_segment = 0
            starting_byte = 0
            ending_byte = 0
            # the headers content-type is automatically set to json after the last request; have to delete it for correct multi-part form post
            del headers["Content-Type"]
            while ending_byte < total_img_size:
                ending_byte = min(total_img_size, starting_byte + chunksize)
                logger.debug(f"{starting_byte}, {ending_byte}")
                upload_append_form = {"command": "APPEND", "media_id": media_id, "segment_index": current_segment}
                upload_file = {
                    "media": ("blob", binary_data[starting_byte:ending_byte]),
                }
                r = self._session.post(url, headers=headers, params=upload_append_form, files=upload_file)

                starting_byte = ending_byte
                current_segment += 1

            # FINALIZE
            # del headers["Content-Type"]
            upload_finalize_form = {"command": "FINALIZE", "media_id": media_id}
            r = self._session.post(url, headers=headers, params=upload_finalize_form)
            logger.info(f"{path} is successfully uploaded! media id: {media_id}")
            return media_id
        except:
            return None

    def _upload_images(self, image_paths=None):
        if image_paths is not None:
            # ignore extra paths
            image_paths = image_paths[:4]
            media_ids = [self._upload_image(image_path) for image_path in image_paths]
            # ignore upload failures
            media_ids = [x for x in media_ids if x is not None]
        else:
            media_ids = None
        return media_ids

    def conversation_control_change(self, tweet_id=None, mode=None):
        # can only be used on the original tweet in a thread
        logger.debug("conversation control change")
        url = "https://twitter.com/i/api/graphql/hb1elGcj6769uT8qVYqtjw/ConversationControlChange"
        headers = self._json_headers()
        form = {
            "variables": {"tweet_id": str(tweet_id), "mode": mode},
            "queryId": queryID_from_url(url),
        }
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            if response.data.tweet_conversation_control_put == "Done":
                logger.info("{tweet_id} conversation control change success!")

    def create_tweet(self, text, image_paths=None, conversation_control=None):
        # conversation_control vals: ByInvitation, Community
        logger.debug("tweet")
        url = "https://twitter.com/i/api/graphql/VtVTvbMKuYFBF9m1s4L1sw/CreateTweet"
        headers = self._tweet_creation_headers()
        media_ids = self._upload_images(image_paths)
        form = self._tweet_creation_form(text, media_ids=media_ids, conversation_control=conversation_control)
        form["queryId"] = queryID_from_url(url)

        # data-raw is used; no url-encoding
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)

            tweet_id = response.data.create_tweet.tweet_results.result.rest_id
            logger.info(f"tweet {tweet_id} is successfully created")
            return tweet_id

    def reply_to_tweet(self, tweet_id, text, image_paths=None):
        logger.debug("reply")
        url = "https://twitter.com/i/api/graphql/VtVTvbMKuYFBF9m1s4L1sw/CreateTweet"
        headers = self._reply_creation_headers()
        media_ids = self._upload_images(image_paths)
        form = self._reply_creation_form(tweet_id, text, media_ids=media_ids)
        form["queryId"] = queryID_from_url(url)

        # data-raw is used; no url-encoding
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)

            reply_id = response.data.create_tweet.tweet_results.result.rest_id
            logger.info(f"tweet {reply_id} in reply to {tweet_id} is successfully created")
            return reply_id

    def create_thread(self, tweets, conversation_control=None, min_interval=10, max_interval=30):
        # tweets: a list of dicts
        initial_tweet = tweets[0]
        rest_tweets = tweets[1:]
        new_tweets_ids = []

        tweet_id = self.create_tweet(initial_tweet["text"], image_paths=initial_tweet["imgs"], conversation_control=conversation_control)
        new_tweets_ids.append(tweet_id)
        sleep(random.randint(min_interval, max_interval))

        for tweet in rest_tweets:
            tweet_id = self.reply_to_tweet(tweet_id, tweet["text"], image_paths=tweet["imgs"])
            new_tweets_ids.append(tweet_id)
            sleep(random.randint(min_interval, max_interval))
        return new_tweets_ids

    def create_scheduled_tweet(self, text, image_paths=None, execute_at=None, in_reply_to=None, quote_from=None):
        """
        Report all users from tweet search result in the same way.

        Parameters:
        text (str): the text content of the tweet
        image_paths (list): a list of full paths of local images
        execute_at (int): future UTC time in utc timestamp
        in_reply_to (int | str): if created as a reply, the tweet_id of the tweet being replied to
        quote_from (int): if created as quote, the tweet_id of the tweet being quoted
        """
        logger.debug("scheduled tweet")
        headers = self._tweet_creation_headers()
        url = "https://twitter.com/i/api/graphql/LCVzRQGxOaGnOnYH01NQXg/CreateScheduledTweet"
        media_ids = self._upload_images(image_paths)

        form = {
          "variables": {
            "post_tweet_request": {
              "auto_populate_reply_metadata": in_reply_to is not None,
              "status": text,
              "exclude_reply_user_ids": [],
              "media_ids": [str(x) for x in media_ids],
            },
            "execute_at": execute_at,
          },
          "queryId": queryID_from_url(url),
        }

        if in_reply_to!=None:
            form["variables"]["post_tweet_request"]["in_reply_to_status_id"] = str(in_reply_to)
        if quote_from!=None:
            quoted_tweet = TwitterBot.tweet_by_rest_id(quote_from)
            quoted_screen_name = quoted_tweet.user.screen_name
            form["variables"]["post_tweet_request"]["attachment_url"] = f"https://twitter.com/{quoted_screen_name}/status/{quote_from}"

        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        if execute_at - current_timestamp < 60:
            #play safe so that it's at least the next minute
            execute_at = current_timestamp + 60
        form["variables"]["execute_at"] = execute_at

        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)

            tweet_id = response.data.tweet.rest_id
            if tweet_id!=None:
                logger.info(f"tweet {tweet_id} is successfully scheduled at {execute_at}")
                return tweet_id

    def delete_scheduled_tweet(self, tweet_id):
        logger.debug("delete scheduled tweet")
        headers = self._json_headers()
        headers["Referer"] = "https://twitter.com/compose/tweet/schedule"
        url = "https://twitter.com/i/api/graphql/CTOVqej0JBXAZSwkp1US0g/DeleteScheduledTweet"
        form = {
          "variables": {
            "scheduled_tweet_id": str(tweet_id),
          },
          "queryId": queryID_from_url(url),
        }

        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)

            if response.data.scheduledtweet_delete == "Done":
                logger.info(f"scheduled tweet {tweet_id} is successfully deleted")
                return True
        return False

    @staticmethod
    def tmp_session_headers():
        if TwitterBot.tmp_count == 0:
            tmp_session = Session()

            tmp_headers = copy.deepcopy(TwitterBot.default_headers)

            del tmp_headers["x-csrf-token"]
            del tmp_headers["x-twitter-auth-type"]

            r = tmp_session.post( "https://api.twitter.com/1.1/guest/activate.json", data=b"", headers=tmp_headers)
            if r.status_code == 200:
                tmp_headers["x-guest-token"] = r.json()["guest_token"]

            # the ct0 value is just a random 32-character string generated from random bytes at client side
            tmp_session.cookies.set("ct0", genct0())
            # set the headers accordingly
            tmp_headers["x-csrf-token"] = tmp_session.cookies.get("ct0")

            tmp_headers["Content-Type"] = "application/json"
            tmp_headers["Host"] = "twitter.com"

            TwitterBot.tmp_session = tmp_session
            TwitterBot.tmp_headers = tmp_headers

        TwitterBot.tmp_count += 1

        if TwitterBot.tmp_count == 100:
            TwitterBot.tmp_count = 0

        return TwitterBot.tmp_session, TwitterBot.tmp_headers

    # @staticmethod
    # def search_timeline_graphql(query):
    def search_timeline_graphql(self, query, batch_count=100):
        # tmp_session, tmp_headers = TwitterBot.tmp_session_headers()
        logger.info("search (graphql, logged in)")

        # url = "https://twitter.com/i/api/graphql/gkjsKepM6gl_HmFWoWKfgg/SearchTimeline"
        url = "https://twitter.com/i/api/graphql/WeHGEHYtJA0sfOOFIBMt8g/SearchTimeline"

        form = {
            "variables": {
                "rawQuery": query,
                "count": batch_count,
                "product": "Latest",
                "querySource": "typed_query",
            },
            "features": TwitterBot.standard_graphql_features,
        }

        form["features"]["blue_business_profile_image_shape_enabled"] = True
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True

        # for entries in TwitterBot._navigate_graphql_entries(SessionType.Guest, url, form):
        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=self._json_headers()):
            yield from TwitterBot._text_from_entries(entries)

    # TODO: not finished
    def search_timeline_login_curl(self, query):
        url = "https://twitter.com/i/api/2/search/adaptive.json"
        form = copy.deepcopy(TwitterBot.adaptive_search_form)

        form["q"] = query
        form["requestContext"] = "launch"
        form["include_ext_profile_image_shape"] = "1"

        headers = copy.deepcopy(self._headers)
        headers["Referer"] = "https://twitter.com/search?q=" + quote(query.encode("utf-8")) + "&src=typed_query&f=live"

        lang = self._session.cookies["lang"]
        ct0 = self._session.cookies["ct0"]
        _twitter_sess = self._session.cookies["_twitter_sess"]
        kdt = self._session.cookies["kdt"]
        auth_token = self._session.cookies["auth_token"]
        twid = self._session.cookies["twid"]

        import subprocess

        curl_command = f"curl 'https://twitter.com/i/api/2/search/adaptive.json?include_profile_interstitial_type=1&include_blocking=1&include_blocked_by=1&include_followed_by=1&include_want_retweets=1&include_mute_edge=1&include_can_dm=1&include_can_media_tag=1&include_ext_has_nft_avatar=1&include_ext_is_blue_verified=1&include_ext_verified_type=1&skip_status=1&cards_platform=Web-12&include_cards=1&include_ext_alt_text=true&include_ext_limited_action_results=false&include_quote_count=true&include_reply_count=1&tweet_mode=extended&include_ext_views=true&include_entities=true&include_user_entities=true&include_ext_media_color=true&include_ext_media_availability=true&include_ext_sensitive_media_warning=true&include_ext_trusted_friends_metadata=true&send_error_codes=true&simple_quoted_tweet=true&count=100&ext=mediaStats%2ChighlightedLabel%2ChasNftAvatar%2CvoiceInfo%2CbirdwatchPivot%2Cenrichments%2CsuperFollowMetadata%2CunmentionInfo%2CeditControl%2Cvibe&tweet_search_mode=live&query_source=typed_query&include_ext_edit_control=true&spelling_corrections=1&pc=1&q={query}&requestContext=launch&include_ext_profile_image_shape=1'    -H 'accept: */*'   -H 'accept-language: en-US,en;q=0.9,fr;q=0.8,zh-CN;q=0.7,zh;q=0.6,zh-TW;q=0.5,ja;q=0.4,es;q=0.3'   -H 'authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'   -H 'cache-control: no-cache'   -H 'cookie:  lang=en; _twitter_sess={_twitter_sess}; kdt={kdt}; auth_token={auth_token}; ct0={ct0}; twid={twid}'   -H 'pragma: no-cache'   -H 'referer: https://twitter.com/search?q={query}&src=typed_query&f=live'   -H 'sec-fetch-dest: empty'   -H 'sec-fetch-mode: cors'   -H 'sec-fetch-site: same-site'   -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:110.0) Gecko/20100101 Firefox/110.0'   -H 'x-csrf-token: {ct0}'   -H 'x-twitter-active-user: yes'   -H 'x-twitter-auth-type: OAuth2Session'   -H 'x-twitter-client-language: en'  -H  'connection: keep-alive' --compressed"
        p = subprocess.Popen(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
        response = json.loads(p)

        response = TwitterJSON(response)
        logger.debug(f"response (curl) {list(response.globalObjects.tweets)[0]}")

    def search_timeline_login_legacy(self, query):
        url = "https://twitter.com/i/api/2/search/adaptive.json"

        headers = copy.deepcopy(self._headers)
        headers["Referer"] = "https://twitter.com/search?q=" + quote(query.encode("utf-8")) + "&src=typed_query&f=live"
        del headers["Host"]  # default: api.twitter.com

        form = copy.deepcopy(TwitterBot.adaptive_search_form)
        form["q"] = query
        # form['requestContext']="launch"
        form["include_ext_profile_image_shape"] = "1"

        while True:
            r = self._session.get(url, headers=headers, params=form)
            if r.status_code != 200:
                break

            logger.info(
                f"x-rate-limit-remaining: {r.headers['x-rate-limit-remaining']} until x-rate-limit-reset: {int(r.headers['x-rate-limit-reset'])-datetime.now(timezone.utc).timestamp()}"
            )
            if int(r.headers["x-rate-limit-remaining"]) == 0:
                sleep(int(r.headers["x-rate-limit-reset"]) - datetime.now(timezone.utc).timestamp() + 1)

            response = r.json()
            response = TwitterJSON(response)

            objects = response.globalObjects
            tweets = objects.tweets
            users = objects.users
            entries = response.timeline.instructions[0].addEntries.entries

            if len(entries) <= 2:
                break

            for tweet_id in tweets:
                tweet = tweets[tweet_id]
                tweet_type = TwitterBot._tweet_type(tweet)
                user_id = tweet.user_id

                user = users[str(user_id)]

                p = TwitterUserProfile(
                    user.id,
                    user.screen_name,
                    created_at=sns_timestamp_from_tweet_timestamp(user.created_at),
                    following_count=user.friends_count,
                    followers_count=user.followers_count,
                    tweet_count=user.statuses_count,
                    media_count=user.media_count,
                    favourites_count=user.favourites_count,
                    display_name=user.name,
                )

                tweet = Tweet(
                    int(tweet_id),
                    tweet_type=tweet_type,
                    created_at=sns_timestamp_from_tweet_timestamp(tweet.created_at),
                    source=tweet.source,
                    text=tweet.full_text,
                    lang=tweet.lang,
                    view_count=tweet.ext_views.count,
                    favorite_count=tweet.favorite_count,
                    reply_count=tweet.reply_count,
                    retweet_count=tweet.retweet_count,
                    quote_count=tweet.quote_count,
                    hashtags=[x["text"] for x in tweet.entities.hashtags],
                    user_mentions=[TwitterUserProfile(x.id, x.screen_name) for x in tweet.entities.user_mentions],
                    user=p,
                )
                if not (("advertiser-interface" in tweet.source) or ("Twitter for Advertisers" in tweet.source)):
                    yield tweet
            bottom_entries = [e for e in entries if "cursor-bottom" in e.entryId]
            replace_instructions = [x for x in response.timeline.instructions if x.replaceEntry is not None]

            if len(bottom_entries) > 0:
                bottom_cursor = [e for e in entries if "cursor-bottom" in e.entryId][0].content.operation.cursor.value
            elif len(replace_instructions) > 0:
                bottom_cursor = [x.replaceEntry.entry for x in replace_instructions if "cursor-bottom" in x.replaceEntry.entryIdToReplace][
                    0
                ].content.operation.cursor.value
            else:
                bottom_cursor = [e for e in entries if e.content.operation is not None and e.content.operation.cursor.cursorType == "Bottom"][
                    0
                ].content.operation.cursor.value

            form["cursor"] = bottom_cursor

            if r.headers["x-rate-limit-remaining"] == 0:
                logger.info("rate limit reached")
                break

        # import subprocess
        # p = subprocess.Popen(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
        # response = json.loads(p)
        # print("\nurl:::",r.url)
        # print("\nheaders:::",r.request.headers)
        # print("\nresponse headers:::", r.headers)

    # @staticmethod
    # def tweet_detail(tweet_id):
    def tweet_detail(self, tweet_id):
        # tmp_session, tmp_headers = TwitterBot.tmp_session_headers()
        logger.debug("get tweet details")

        url = "https://twitter.com/i/api/graphql/7d8fexGPbM0BRc5DkacJqA/TweetDetail"
        form = copy.deepcopy(TwitterBot.tweet_detail_form)

        form["variables"]["focalTweetId"] = str(tweet_id)
        form["features"]["blue_business_profile_image_shape_enabled"] = False
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True

        # for entries in TwitterBot._navigate_graphql_entries(SessionType.Guest, url, form):
        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=self._json_headers()):
            if not entries:  # cannot use is None here because None is wrapped in TwitterJSON
                return None
            else:
                yield from TwitterBot._text_from_entries(entries)  # currently ignores post from advertiser even if it's the main post

    @staticmethod
    def cdn_tweet_detail(tweet_id):
        logger.debug("get tweet brief from twitter cdn")
        url = "https://cdn.syndication.twimg.com/tweet-result"
        form = {"id": tweet_id, "lang": "en"}
        form["token"] = ""
        headers = {
            "Accept": "*/*",
            "Origin": "https://platform.twitter.com",
            "Referer": "https://platform.twitter.com/",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        }
        try:
            r = requests.get(url, headers=headers, params=form)
            r.raise_for_status()
            response = r.json()
            response = TwitterJSON(response)
            #print(tweet_id,r.text)

            if response.__typename == "TweetTombstone":
                return None

            this_id = int(response.id_str)

            user = response.user
            p = TwitterUserProfile(
                int(user.id_str),
                user.screen_name,
                display_name=user.name,
            )
            otherinfo = dict()
            # if it's a retweet, platform.twitter will just return the tweet being retweeted
            # not a retweet
            if this_id == tweet_id:
                otherinfo["user"] = p
                if response.in_reply_to_status_id_str:
                    otherinfo["replied_tweet_id"] = int(response.in_reply_to_status_id_str)
                if response.in_reply_to_user_id_str:
                    otherinfo["replied_user_id"] = int(response.in_reply_to_user_id_str)
                quoted_tweet = response.quoted_tweet
                if quoted_tweet:
                    otherinfo["quoted_tweet_id"] = int(quoted_tweet.id_str)
                    otherinfo["quoted_user_id"] = int(quoted_tweet.user.id_str)
            # a retweet
            else:
                otherinfo["retweeted_tweet_id"] = this_id
                otherinfo["retweeted_user_id"] = int(user.id_str)
            media = []
            if response.mediaDetails:
                for m in response.mediaDetails:
                    media_type = m.type
                    if media_type == "photo":
                        url = m.media_url_https
                    elif media_type == "video" or media_type == "animated_gif":
                        variants = m.video_info.variants
                        highest_bitrate_variant_url = max(variants, key=lambda x: x.get("bitrate", 0))["url"]
                        url = highest_bitrate_variant_url.split("?")[0].strip()
                    media.append({"type": media_type, "url": url})

            tweet = Tweet(
                int(tweet_id),
                tweet_type=TwitterBot._cdn_tweet_type(otherinfo),
                created_at=datetime.strptime(response.created_at, "%Y-%m-%dT%H:%M:%S.%f%z").replace(tzinfo=timezone.utc).isoformat(),
                text=response.text,
                lang=response.lang,
                hashtags=[x["text"] for x in response.entities.hashtags],
                media=media,
                user_mentions=[TwitterUserProfile(int(x.id_str), x.screen_name) for x in response.entities.user_mentions],
                **otherinfo,
            )
            return tweet
        except:
            return None

    def pin_tweet(self, tweet_id):
        logger.debug("pin tweet")
        url = "https://api.twitter.com/1.1/account/pin_tweet.json"
        form = {"tweet_mode": "extended", "id": tweet_id}
        r = self._session.post(url, headers=self._headers, params=form)
        if r.status_code == 200:
            logger.info(f"{tweet_id} pinned!")

    def get_blocked(self):
        """
        Get the list of blocked accounts.
        """
        url = "https://twitter.com/i/api/graphql/kpS7GZQ96pe3n5dIzKS2wg/BlockedAccountsAll"
        form = copy.deepcopy(TwitterBot.blocklist_form)
        form["features"]["responsive_web_media_download_video_enabled"] = False
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True
        headers = self._json_headers()

        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._users_from_entries(entries)

    def get_muted(self):
        """
        Get the list of muted accounts
        """
        url = "https://twitter.com/i/api/graphql/g40AoFEAdKggdYivmA2bSg/MutedAccounts"
        form = copy.deepcopy(TwitterBot.blocklist_form)
        form["features"]["responsive_web_media_download_video_enabled"] = False
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True
        headers = self._json_headers()

        for entries in self._navigate_graphql_entries(SessionType.Authenticated, url, form, session=self._session, headers=headers):
            yield from self._users_from_entries(entries)

    def get_current_id(self):
        """
        Returns the numerical id of the current account
        """
        current_id = unquote(self._session.cookies["twid"]).replace('"', "")
        current_id = int(current_id.split("=")[1])
        return current_id

    def unsubscribe_email(self):
        """
        Turns off email notifications
        """
        url = "https://twitter.com/i/api/graphql/2qKKYFQift8p5-J1k6kqxQ/WriteEmailNotificationSettings"
        form = {
            "queryId": queryID_from_url(url),
            "variables": {
                "settings": {
                    "send_twitter_emails": False,
                },
                "userId": self.get_current_id(),
            },
        }
        headers = self._json_headers()

        r = self._session.post(url, headers=headers, data=json.dumps(form))
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            if response.data.user_notifications_email_notifications_put == "Done":
                logger.info("{tweet_id} email notification change success!")

    def set_protected_status(self, protected = False):
        url = "https://api.twitter.com/1.1/account/settings.json"
        form = {
            "include_mention_filter": True,
            "include_nsfw_user_flag": True,
            "include_nsfw_admin_flag": True,
            "include_ranked_timeline": True,
            "include_alt_text_compose": True,
            "protected": protected,
        }
        headers = copy.deepcopy(self._headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        r = self._session.post(url, headers=headers, data=urlencode(form))
        if r.status == 200:
            response = r.json()
            response = TwitterJSON(response)
            if response.protected == protected:
                logger.info(f"successfully changed protected status to {protected}")

    @staticmethod
    def tweet_by_rest_id(tweet_id):
        url = "https://twitter.com/i/api/graphql/0hWvDhmW8YQ-S_ib3azIrw/TweetResultByRestId"
        form = {
            "variables":{"tweetId":str(tweet_id),"withCommunity":False,"includePromotedContent":False,"withVoice":False},
            "features":TwitterBot.standard_graphql_features
        }
        form["features"]["responsive_web_media_download_video_enabled"] = False
        form["features"]["longform_notetweets_rich_text_read_enabled"] = True

        tmp_session, tmp_headers = TwitterBot.tmp_session_headers()
        encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})

        r = tmp_session.get(url, headers=tmp_headers, params=encoded_params)
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            #if the tweet has been deleted, response.data.tweetResult.result would be None and _tweet_from_result would return None
            return TwitterBot._tweet_from_result(response.data.tweetResult.result)

    @staticmethod
    @cache
    #def user_by_screen_name(self, screen_name):
    def user_by_screen_name(screen_name):
        """
        Returns the account status and the user profile, given user's screen_name.
        """
        tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        url = "https://twitter.com/i/api/graphql/k26ASEiniqy4eXMdknTSoQ/UserByScreenName"
        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"] = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        form["features"]["blue_business_profile_image_shape_enabled"] = False

        encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})
        r = tmp_session.get(url, headers=tmp_headers, params=encoded_params)
        #r = self._session.get(url, headers=self._json_headers(), params=encoded_params)
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            return TwitterBot._status_and_user_from_result(response.data.user.result)

    #@staticmethod
    @cache
    def user_by_id(self, user_id):
    #def user_by_id(user_id):
        """
        Returns the account status and the user profile, given user's id.
        """
        #tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        url = "https://twitter.com/i/api/graphql/nI8WydSd-X-lQIVo6bdktQ/UserByRestId"
        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"] = {"userId": str(user_id), "withSafetyModeUserFields": True}

        encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})

        #r = tmp_session.get(url, headers=tmp_headers, params=encoded_params)
        r = self._session.get(url, headers=self._json_headers(), params=encoded_params)
        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            return TwitterBot._status_and_user_from_result(response.data.user.result)

    @staticmethod
    def status_by_screen_name(screen_name):
    #def status_by_screen_name(self, screen_name):
        """
        Probe the status of an account, given user's screen_name.
        """
        values = TwitterBot.user_by_screen_name(screen_name)
        #values = self.user_by_screen_name(screen_name)
        if values:
            status, user_profile = values
            return status

    # @staticmethod
    # def status_by_id(user_id):
    def status_by_id(self, user_id):
        """
        Probe the status of an account, given user's id.
        """
        # values = TwitterBot.user_by_id(user_id)
        values = self.user_by_id(user_id)
        if values:
            status, user_profile = values
            return status

    @staticmethod
    def id_from_screen_name(screen_name):
    #def id_from_screen_name(self, screen_name):
        """
        Convert user id to screen name
        """
        values = TwitterBot.user_by_screen_name(screen_name)
        #values = self.user_by_screen_name(screen_name)
        if values:
            status, user_profile = values
            return user_profile.user_id

    # @staticmethod
    # def screen_name_from_id(user_id):
    def screen_name_from_id(self, user_id):
        """
        Convert screen name to user id
        """
        # values = TwitterBot.user_by_id(user_id)
        values = self.user_by_id(user_id)
        if values:
            status, user_profile = values
            return user_profile.screen_name

    @staticmethod
    def numerical_id(user_id):
        try:
            int_user_id = int(user_id)
        except:
            int_user_id = int(TwitterBot.id_from_screen_name(user_id))

        return int_user_id


if __name__ == "__main__":
    pass
