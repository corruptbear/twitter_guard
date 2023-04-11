import os
import sys
import traceback

import requests
from urllib.parse import urlencode, quote

import dataclasses

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
from .report import ReportHandler
from time import sleep

import snscrape.modules.twitter as sntwitter

from collections import abc
import keyword


def display_session_cookies(s):
    display_msg("print cookies")
    for x in s.cookies:
        print(x)


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
    except Exception as e:
        print(e)
        result = rule_eval(default_rule, rule_eval_vars)

    return result


class TwitterJSON:
    def __new__(cls, arg):
        if isinstance(arg, abc.Mapping):
            return super().__new__(cls)
        elif isinstance(arg, abc.MutableSequence):
            return [cls(item) for item in arg]
        else:
            return arg

    def __init__(self, mapping):
        self.__data = {}
        for key, value in mapping.items():
            if keyword.iskeyword(key):
                key += "_"
            self.__data[key] = value

    def __getattr__(self, name):
        try:
            # convert the mangled __typename back to original value
            if "__typename" in name:
                name = "__typename"
            # no ambiguity
            if name != "items":
                return getattr(self.__data, name)
            # we are only in the data, not the built-in method
            else:
                raise AttributeError
        except AttributeError:
            if name in self.__data:
                return TwitterJSON(self.__data[name])
            return None

    # still supports subscription, just in case
    def __getitem__(self, name):
        return self.__getattr__(name)

    def __dir__(self):
        return self.__data.keys()

    def __repr__(self):
        return str(self.__data)

    def __len__(self):
        return len(self.__data)

    def __contains__(self, key):
        """
        called when `in` operation is used.
        """
        return key in self.__data

    def __iter__(self):
        return (key for key in self.__data)

    def values(self):
        return (TwitterJSON(x) for x in self.__data.values())


@dataclasses.dataclass
class TwitterUserProfile:
    user_id: int
    screen_name: str
    created_at: str = dataclasses.field(default=None)
    following_count: int = dataclasses.field(default=None)
    followers_count: int = dataclasses.field(default=None)
    tweet_count: int = dataclasses.field(default=None)
    media_count: int = dataclasses.field(default=None)
    favourites_count: int = dataclasses.field(default=None)
    days_since_registration: int = dataclasses.field(init=False, default=None)
    display_name: str = dataclasses.field(default=None, metadata={"keyword_only": True})

    def __post_init__(self):
        if self.created_at is not None:
            current_time = datetime.now(timezone.utc)
            created_time = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc).astimezone(tz.gettz())
            time_diff = current_time - created_time
            self.days_since_registration = time_diff.days


@dataclasses.dataclass
class Tweet:
    tweet_id: int
    tweet_type: str = dataclasses.field(default=None)
    created_at: str = dataclasses.field(default=None)
    source: str = dataclasses.field(default=None)
    text: str = dataclasses.field(default=None)


class TwitterLoginBot:
    def __init__(self, email, password, screenname, phonenumber, cookie_path=None):
        self._headers = {
            "Host": "api.twitter.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
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
            "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "Connection": "keep-alive",
            "TE": "trailers",
        }

        self._session = requests.Session()

        self._cookie_path = cookie_path

        self._email = email
        self._password = password
        self._screenname = screenname
        self._phonenumber = phonenumber

        self._init_forms()

        # get the flow_token
        self.get_login_flow_token()

        while int(self.login_flow_token.split(":")[-1]) != 17:
            self._do_task()

        # one more time to get longer ct0
        display_msg("update to full ct0")
        self._do_task()

        # save the cookies for reuse
        self.save_cookies()

        print("")

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
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:11",
            "subtask_inputs": [
                {
                    "subtask_id": "AccountDuplicationCheck",
                    "check_logged_in_account": {"link": "AccountDuplicationCheck_false"},
                }
            ],
        }

        self.get_full_ct0_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:17",
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
            "flow_token": "g;167669570499095475:-1676695708216:wfmlDaSgvN5ydOS4EI5oJvr6:7",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginEnterAlternateIdentifierSubtask",
                    "enter_text": {"text": self._screenname, "link": "next_link"},
                }
            ],
        }

        self.enter_password_payload = {
            "flow_token": "g;167658632144249788:-1676586337028:ZJlPGfGY6fmt0YNIvwX5MhR5:8",
            "subtask_inputs": [
                {
                    "subtask_id": "LoginEnterPassword",
                    "enter_password": {"password": self._password, "link": "next_link"},
                }
            ],
        }

        # may be useful in the future if the mapping if subject to change
        self.tasks = {
            0: {"name": "LoginJsInstrumentationSubtask", "payload": self.get_sso_payload},
            1: {"name": "LoginEnterUserIdentifierSSO", "payload": self.enter_email_payload},
            7: {"name": "LoginEnterAlternateIdentifierSubtask", "payload": self.enter_alternative_id_payload},
            8: {"name": "LoginEnterPassword", "payload": self.enter_password_payload},
            11: {"name": "AccountDuplicationCheck", "payload": self.account_duplication_check_payload},
            17: {"name": "LoginSuccessSubtask", "payload": self.get_full_ct0_payload},
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

    def save_cookies(self):
        # convert the cookiejar object to a dictionary; among duplicated entries, only the latest entry is kept
        cookie_dict = requests.utils.dict_from_cookiejar(self._session.cookies)
        # convert the dictionary back to a cookiejar object
        unique_cookiejar = requests.utils.cookiejar_from_dict(cookie_dict)

        self._session.cookies = unique_cookiejar

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
        display_msg("cookies from requests saved")

    def _prepare_next_login_task(self, r):
        print(r.status_code)
        j = r.json()
        self.login_flow_token = j["flow_token"]
        subtasks = j["subtasks"]

        print("flow_token:", self.login_flow_token)

        for s in subtasks:
            print(s["subtask_id"])

    def _do_task(self):
        task = int(self.login_flow_token.split(":")[-1])
        display_msg(self.tasks[task]["name"])

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

            r = self._session.post(
                "https://api.twitter.com/1.1/onboarding/task.json",
                headers=self._headers,
                data=json.dumps(self.get_sso_payload),
            )

        else:
            payload = self.tasks[task]["payload"]

            payload["flow_token"] = self.login_flow_token

            r = self._session.post(
                "https://api.twitter.com/1.1/onboarding/task.json",
                headers=self._headers,
                data=json.dumps(payload),
            )

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
            display_msg("cannot find guest token from the webpage")
            r = self._session.post("https://api.twitter.com/1.1/guest/activate.json", data=b"", headers=self._headers)
            if r.status_code == 200:
                self._headers["x-guest-token"] = r.json()["guest_token"]
                display_msg("got guest token from the endpoint")

        # the ct0 value is just a random 32-character string generated from random bytes at client side
        self._session.cookies.set("ct0", genct0())

        # set the headers accordingly
        self._headers["x-csrf-token"] = self._session.cookies.get("ct0")

        # display_session_cookies(self._session)

        r = self._session.post(
            "https://api.twitter.com/1.1/onboarding/task.json?flow_name=login",
            headers=self._headers,
            params=self.get_token_payload,
        )

        self._prepare_next_login_task(r)

        # att is set by the response cookie


class TwitterBot:
    urls = {
        "badge_count": "https://api.twitter.com/2/badge_count/badge_count.json",
        "notification_all": "https://api.twitter.com/2/notifications/all.json",
        "jot_url": "https://api.twitter.com/1.1/jot/client_event.json",
        "last_seen_cursor": "https://api.twitter.com/2/notifications/all/last_seen_cursor.json",
        "block": "https://api.twitter.com/1.1/blocks/create.json",
        "unblock": "https://api.twitter.com/1.1/blocks/destroy.json",
        "retweeters": "https://twitter.com/i/api/graphql/ViKvXirbgcKs6SfF5wZ30A/Retweeters",
        "followers": "https://twitter.com/i/api/graphql/utPIvA97eaEvxfra_PQz_A/Followers",
        "following": "https://twitter.com/i/api/graphql/AmvGuDw_fxEbJtEXie4OkA/Following",
        "tweets_replies": "https://twitter.com/i/api/graphql/pNl8WjKAvaegIoVH--FuoQ/UserTweetsAndReplies",
        "user_by_rest_id": "https://twitter.com/i/api/graphql/nI8WydSd-X-lQIVo6bdktQ/UserByRestId",
        "user_by_screen_name": "https://twitter.com/i/api/graphql/k26ASEiniqy4eXMdknTSoQ/UserByScreenName",
    }

    jot_form_success = {
        "keepalive": "false",
        "category": "perftown",
        "log": '[{"description":"rweb:urt:notifications:fetch_Top:success","product":"rweb","duration_ms":73},{"description":"rweb:urt:notifications:fetch_Top:format:success","product":"rweb","duration_ms":74}]',
    }

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
        "include_ext_collab_control": "true",
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
        "cursor": "DAABDAABCgABAAAAABZfed0IAAIAAAABCAADYinMQAgABFMKJicACwACAAAAC0FZWlhveW1SNnNFCAADjyMIvwAA",
        "ext": "mediaStats,highlightedLabel,hasNftAvatar,voiceInfo,birdwatchPivot,enrichments,superFollowMetadata,unmentionInfo,editControl,collab_control,vibe",
    }

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
        "queryId": "VtVTvbMKuYFBF9m1s4L1sw",
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
            "withSuperFollowsUserFields": True,
            "withDownvotePerspective": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "withSuperFollowsTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        },
        "features": standard_graphql_features,
    }

    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:110.0) Gecko/20100101 Firefox/110.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
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
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "Connection": "keep-alive",
        "TE": "trailers",
    }

    def __init__(self, cookie_path=None, config_path=None, white_list_path=None, block_list_path=None):
        """
        In order to save the list of newly blocked accounts, the block_list_path should be specified, even if you have not created that file.
        """
        self._headers = copy.deepcopy(TwitterBot.default_headers)

        self._session = requests.Session()

        self._cookie_path = cookie_path
        self._config_path = config_path
        self._config_dict = load_yaml(config_path)

        self._block_list_path = block_list_path

        self._block_list = load_yaml(self._block_list_path)

        self._white_list_path = white_list_path

        self._white_list = load_yaml(self._white_list_path)

        self._filtering_rule = self._config_dict["filtering_rule"]

        try:
            self._load_cookies()
        except:
            # if the cookie does not exist
            traceback.print_exc()
            self.refresh_cookies()

        # display_session_cookies(self._session)

        # when disabled, will use the default cursor
        self._load_cursor()

        self.reporter = ReportHandler(self._headers, self._session)

    def _set_selenium_cookies(self, cookies):
        display_msg("setting cookies")
        for x in cookies:
            print(x)
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
        display_msg("loading cookies")
        cookies = pickle.load(open(self._cookie_path, "rb"))
        self._set_selenium_cookies(cookies)

    def refresh_cookies(self):
        """
        Try to get the cookies through requests only TwitterLoginBot first.
        If it does not work, use SeleniumTwitterBot to get the cookies
        """
        try:
            display_msg("trying using requests to get cookies")
            b = TwitterLoginBot(
                self._config_dict["login"]["email"],
                self._config_dict["login"]["password"],
                self._config_dict["login"]["screenname"],
                self._config_dict["login"]["phonenumber"],
                cookie_path=self._cookie_path,
            )
            self._load_cookies()
        except:
            display_msg("trying using selenium to get cookies")
            b = SeleniumTwitterBot(config_path=self._config_path, cookie_path=self._cookie_path)
            # new cookie will be saved from selenium
            b.twitter_login()
            b.save_cookies()

            self._set_selenium_cookies(b.driver.get_cookies())

    def get_badge_count(self):
        display_msg("get badge count")

        # display_session_cookies(self._session)
        url = TwitterBot.urls["badge_count"]
        badge_form = TwitterBot.badge_form
        r = self._session.get(url, headers=self._headers, params=badge_form)
        print(r.status_code, r.json())

    def update_local_cursor(self, val):
        TwitterBot.notification_all_form["cursor"] = val
        self._config_dict["latest_cursor"] = val

        save_yaml(self._config_dict, self._config_path, "w")

    def _load_cursor(self):
        if len(self._config_dict["latest_cursor"].strip()) > 0:
            TwitterBot.notification_all_form["cursor"] = self._config_dict["latest_cursor"]
        print("after loading cursor:", TwitterBot.notification_all_form["cursor"])

    def update_remote_cursor(self, val):
        url = TwitterBot.urls["last_seen_cursor"]
        cursor_form = {"cursor": val}
        r = self._session.post(url, headers=self._headers, params=cursor_form)
        print(r.status_code, r.text)

    def update_remote_latest_cursor(self):
        """
        Updates the top cursor value in the API, using self.latest_cursor.

        This function does not take any arguments and does not return a value.

        The badge will disappear after you refresh in a non-notification page
        """

        self.update_remote_cursor(TwitterBot.notification_all_form["cursor"])

    def block_user(self, user_id):
        user_id = numerical_id(user_id)

        url = TwitterBot.urls["block"]
        block_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=block_form)
        if r.status_code == 200:
            print("successfully sent block post!")
        display_msg("block")
        print(r.status_code, r.text)

    def unblock_user(self, user_id):
        user_id = numerical_id(user_id)

        url = TwitterBot.urls["unblock"]
        unblock_form = {"user_id": str(user_id)}
        r = self._session.post(url, headers=self._headers, params=unblock_form)
        if r.status_code == 200:
            print("successfully sent unblock post!")
        display_msg("unblock")
        print(r.status_code, r.text)

    def judge_users(self, users):
        """
        Examine users coming from the notifications one by one.
        Block bad users. Update the local block list.
        """

        # ignore user already in block_list or white_list
        sorted_users = {user_id: users[user_id] for user_id in users if (user_id not in self._block_list) and (user_id not in self._white_list)}

        for user_id in sorted_users:
            user = sorted_users[user_id]

            is_bad = oracle(user, self._filtering_rule)

            conclusion_str = "bad" if is_bad else "good"

            if is_bad:
                self.block_user(user_id)

                self._block_list[user.user_id] = user.screen_name
                save_yaml(self._block_list, self._block_list_path, "w")

            print(
                f"ORACLE TIME!: id {user.user_id:<25} name {user.screen_name:<16} followers_count {user.followers_count:<10} days_since_reg {user.days_since_registration:<5} is {conclusion_str}"
            )

    def check_notifications(self, block=True):
        """
        Gets the recent notifications from the endpoint.

        Whenever there is new notification, or you perform operations like block/unblock, mute/unmute, you will get new stuff here.

        Updates latest_cursor using the top cursor fetched. After the update, if no new thing happens, then you will not get anything here.

        Block bad users.

        """
        url = TwitterBot.urls["notification_all"]
        notification_all_form = TwitterBot.notification_all_form
        r = self._session.get(url, headers=self._headers, params=notification_all_form)

        display_msg("notifications/all.json")
        print(f"status_code: {r.status_code}, length: {r.headers['content-length']}")

        result = r.json()
        result = TwitterJSON(result)

        print("result keys:", result.keys())

        convo = set()
        tweets, notifications = [], []

        print("globalObjects keys:", result.globalObjects.keys(), "\n")

        logged_users = {}

        if result.globalObjects.users:
            users = result.globalObjects.users
            # annoying: cannot use variable in dot attribute getter
            for user in users.values():
                p = TwitterUserProfile(
                    user.id,
                    user.screen_name,
                    created_at=user.created_at,
                    following_count=user.friends_count,
                    followers_count=user.followers_count,
                    tweet_count=user.statuses_count,
                    media_count=user.media_count,
                    favourites_count=user.favourites_count,
                    display_name=user.name,
                )
                # print(dataclasses.asdict(p))
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
        entryid_notification_users = {}

        display_msg("globalObjects['notifications']")
        if result.globalObjects.notifications:
            notifications = result.globalObjects.notifications
            # userid and sortindex available; but not interaction type
            for notification in notifications.values():
                # print(notification)
                # print(notification.message.text)
                for e in notification.message.entities:
                    entry_user_id = int(e.ref.user.id)
                    # add the users appearing in notifications (do not include replies)
                    entryid_notification_users[notification.id] = entry_user_id

        display_msg("timeline")
        print("TIMELINE ID", result.timeline.id)
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

        display_msg("timeline: non_cursor_notification")
        # users_liked_your_tweet/user_liked_multiple_tweets/user_liked_tweets_about_you/generic_login_notification/generic_report_received/users_retweeted_your_tweet ; no userid is included in these entries
        for entry in non_cursor_notification_entries:
            # print(entry)
            if entry.content.item.clientEventInfo.element not in ["generic_login_notification", "generic_report_received"]:
                entry_id = entry.entryId[13:]
                entry_user_id = entryid_notification_users[entry_id]
                print(entry.sortIndex, entry.content.item.clientEventInfo.element, entry_user_id)
                interacting_users[entry_id] = {
                    "sort_index": entry.sortIndex,
                    "user_id": entry_user_id,
                    "user": logged_users[entry_user_id],
                    "event_type": entry.content.item.clientEventInfo.element,
                }

        display_msg("timeline: non_cursor_tweets")
        # user_replied_to_your_tweet/user_quoted_your_tweet
        for entry in non_cursor_tweet_entries:
            entry_id = entry.entryId[13:]
            entry_user_id = id_indexed_tweets[int(entry.content.item.content.tweet.id)].user_id
            print(entry.sortIndex, entry.content.item.clientEventInfo.element, entry_user_id)
            # add the users replying to me
            interacting_users[entry_id] = {
                "sort_index": entry.sortIndex,
                "user_id": entry_user_id,
                "user": logged_users[entry_user_id],
                "event_type": entry.content.item.clientEventInfo.element,
            }

        display_msg("all interactions")
        # sort by time from latest to earliest
        for x in sorted(interacting_users.items(), key=lambda item: item[1]["sort_index"], reverse=True):
            print(f"{x[1]['user'].screen_name:<16} {x[1]['event_type']}")

        display_msg("check users interacting with me")
        """
        print("\ntweets VS non_cursor_entries", len(tweets), len(non_cursor_entries))
        print(
            "notifications VS non_cursor_notification",
            len(notifications),
            len(non_cursor_notification_entries),
        )
        print("number of convos", len(convo))
        """
        display_msg("cursors")
        for entry in cursor_entries:
            cursor = entry.content.operation.cursor
            print(entry.sortIndex, cursor)
            if cursor.cursorType == "Top":
                self.latest_sortindex = entry.sortIndex

                self.update_local_cursor(cursor.value)
                # self.update_remote_latest_cursor()  # will cause the badge to disappear
        if block:
            self.judge_users({interacting_users[entry_id]["user_id"]: interacting_users[entry_id]["user"] for entry_id in interacting_users})

    def _cursor_from_entries(self, entries):
        for e in entries[-2:]:
            content = e.content
            if content.entryType == "TimelineTimelineCursor":
                if content.cursorType == "Bottom":
                    return content.value

    def _users_from_entries(self, entries):
        for e in entries:
            content = e.content
            if content.entryType == "TimelineTimelineItem":
                r = content.itemContent.user_results.result

                if content.itemContent.user_results.result.__typename == "User":
                    user = content.itemContent.user_results.result.legacy

                    p = TwitterUserProfile(
                        int(e.entryId.split("-")[1]),
                        user.screen_name,
                        created_at=user.created_at,
                        following_count=user.friends_count,
                        followers_count=user.followers_count,
                        tweet_count=user.statuses_count,
                        media_count=user.media_count,
                        favourites_count=user.favourites_count,
                        display_name=user.name,
                    )

                    yield p

                else:
                    # otherwise the typename is UserUnavailable
                    print("cannot get user data", e.entryId)

    def _tweet_type(self, in_reply_to_screen_name, is_quote_status, retweeted):
        if in_reply_to_screen_name is not None:
            if is_quote_status:
                return "reply_by_quote"
            else:
                return "reply"
        else:
            if is_quote_status:
                return "quote"
            if retweeted:
                return "retweeted"
            return "original"

    def _text_from_entries(self, entries, user_id):
        for e in entries:
            content = e.content

            if content.entryType == "TimelineTimelineModule":
                for i in content.items:
                    result = i.item.itemContent.tweet_results.result
                    if result:
                        if result.__typename == "Tweet":
                            # other user's post in a conversation is also returned; needs filtering here
                            if int(result.core.user_results.result.rest_id) == user_id:
                                tweet_type = self._tweet_type(
                                    result.legacy.in_reply_to_screen_name, result.legacy.is_quote_status, result.legacy.retweeted
                                )
                                tweet = Tweet(
                                    result.rest_id,
                                    tweet_type=tweet_type,
                                    created_at=result.legacy.created_at,
                                    source=result.source,
                                    text=result.legacy.full_text,
                                )
                                yield tweet
                        if result.__typename == "TweetWithVisibilityResults":
                            try:
                                tweet_type = self._tweet_type(
                                    result.tweet.legacy.in_reply_to_screen_name, result.tweet.legacy.is_quote_status, result.tweet.legacy.retweeted
                                )
                                tweet = Tweet(
                                    result.tweet.rest_id,
                                    tweet_type=tweet_type,
                                    created_at=result.tweet.legacy.created_at,
                                    source=result.tweet.source,
                                    text=result.tweet.legacy.full_text,
                                )
                            except:
                                traceback.print_exc()
                                print(result)
                            yield tweet
            elif content.entryType == "TimelineTimelineItem":
                result = content.itemContent.tweet_results.result
                if result:
                    if result.__typename == "Tweet":
                        tweet_type = self._tweet_type(result.legacy.in_reply_to_screen_name, result.legacy.is_quote_status, result.legacy.retweeted)
                        tweet = Tweet(
                            result.rest_id,
                            tweet_type=tweet_type,
                            created_at=result.legacy.created_at,
                            source=result.source,
                            text=result.legacy.full_text,
                        )
                        yield tweet
                    if result.__typename == "TweetWithVisibilityResults":
                        try:
                            tweet_type = self._tweet_type(
                                result.tweet.legacy.in_reply_to_screen_name, result.tweet.legacy.is_quote_status, result.tweet.legacy.retweeted
                            )
                            tweet = Tweet(
                                result.tweet.rest_id,
                                tweet_type=tweet_type,
                                created_at=result.tweet.legacy.created_at,
                                source=result.tweet.source,
                                text=result.tweet.legacy.full_text,
                            )
                        except:
                            traceback.print_exc()
                            print(result)
                        yield tweet

    def _json_headers(self):
        headers = copy.deepcopy(self._headers)
        headers["Content-Type"] = "application/json"
        headers["Host"] = "twitter.com"

        return headers

    def _navigate_graphql_entries(self, session, url, headers, form):
        while True:
            encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})
            r = session.get(url, headers=headers, params=encoded_params)

            response = r.json()
            response = TwitterJSON(response)

            data = response.data

            if data.retweeters_timeline:
                instructions = data.retweeters_timeline.timeline.instructions
            else:
                result = data.user.result
                if result.timeline_v2:
                    instructions = result.timeline_v2.timeline.instructions
                else:
                    instructions = result.timeline.timeline.instructions

            entries = [x for x in instructions if x.type == "TimelineAddEntries"][0].entries

            if len(entries) <= 2:
                break

            yield entries

            bottom_cursor = self._cursor_from_entries(entries)
            form["variables"]["cursor"] = bottom_cursor

    # TODO: this could be done login free
    def get_tweets_replies(self, user_id):
        """
        Gets the texts from the user's tweets and replies tab.
        """
        user_id = numerical_id(user_id)

        # headers = self._json_headers()
        url = TwitterBot.urls["tweets_replies"]

        tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"]["userId"] = str(user_id)

        for entries in self._navigate_graphql_entries(tmp_session, url, tmp_headers, form):
            yield from self._text_from_entries(entries, user_id)

    def get_following(self, user_id):
        """
        Gets the list of following.
        Returns a list of TwitterUserProfile.
        """
        user_id = numerical_id(user_id)

        display_msg("get following")

        headers = self._json_headers()

        url = TwitterBot.urls["following"]

        form = copy.deepcopy(TwitterBot.following_followers_form)

        # set userID in form
        form["variables"]["userId"] = str(user_id)

        for entries in self._navigate_graphql_entries(self._session, url, headers, form):
            yield from self._users_from_entries(entries)

    def get_followers(self, user_id):
        """
        Gets the list of followers.
        Returns a list of TwitterUserProfile.
        """
        user_id = numerical_id(user_id)

        display_msg("get followers")

        headers = self._json_headers()

        url = TwitterBot.urls["followers"]

        form = copy.deepcopy(TwitterBot.following_followers_form)

        # set userID in form
        form["variables"]["userId"] = str(user_id)

        for entries in self._navigate_graphql_entries(self._session, url, headers, form):
            yield from self._users_from_entries(entries)

    def get_retweeters(self, tweet_url):
        """
        Gets the list of visible (not locked) retweeters.
        Returns a list of TwitterUserProfile.
        """
        # needs to have the br decoding library installed for requests to handle br compressed results

        display_msg("get retweeters")

        headers = self._json_headers()

        url = TwitterBot.urls["retweeters"]

        form = copy.deepcopy(TwitterBot.following_followers_form)
        del form["variables"]["userId"]
        # del form["features"]["longform_notetweets_richtext_consumption_enabled"]

        # set tweetId in form
        form["variables"]["tweetId"] = tweet_url.split("/")[-1]

        for entries in self._navigate_graphql_entries(self._session, url, headers, form):
            yield from self._users_from_entries(entries)

    def _tweet_creation_form(self, text):
        form = copy.deepcopy(TwitterBot.create_tweet_form)
        form["variables"]["tweet_text"] = text

        form["features"]["view_counts_everywhere_api_enabled"] = False
        del form["features"]["responsive_web_twitter_blue_verified_badge_is_enabled"]
        form["features"]["blue_business_profile_image_shape_enabled"] = False
        form["features"]["responsive_web_graphql_exclude_directive_enabled"] = True

        return form

    def _reply_creation_form(self, tweet_id, text):
        form = self._tweet_creation_form(text)
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

    def create_tweet(self, text):
        display_msg("tweet")

        headers = self._tweet_creation_headers()
        form = self._tweet_creation_form(text)

        url = "https://twitter.com/i/api/graphql/VtVTvbMKuYFBF9m1s4L1sw/CreateTweet"

        # data-raw is used; no url-encoding
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        print(r.status_code, r.text)

        response = r.json()
        response = TwitterJSON(response)

        if r.status_code == 200:
            return response.data.create_tweet.tweet_results.result.rest_id

    def reply_to_tweet(self, tweet_id, text):
        display_msg("reply")

        headers = self._reply_creation_headers()
        form = self._reply_creation_form(tweet_id, text)

        url = "https://twitter.com/i/api/graphql/VtVTvbMKuYFBF9m1s4L1sw/CreateTweet"

        # data-raw is used; no url-encoding
        r = self._session.post(url, headers=headers, data=json.dumps(form))
        print(r.status_code)

        response = r.json()
        response = TwitterJSON(response)

        if r.status_code == 200:
            return response.data.create_tweet.tweet_results.result.rest_id

    def create_thread(self, texts):
        initial_text = texts[0]
        rest_texts = texts[1:]

        tweet_id = self.create_tweet(initial_text)
        sleep(random.randint(10, 30))

        for text in rest_texts:
            tweet_id = self.reply_to_tweet(tweet_id, text)
            sleep(random.randint(10, 30))

    @staticmethod
    def tmp_session_headers():
        tmp_session = requests.Session()

        tmp_headers = copy.deepcopy(TwitterBot.default_headers)

        del tmp_headers["x-csrf-token"]
        del tmp_headers["x-twitter-auth-type"]

        r = tmp_session.post("https://api.twitter.com/1.1/guest/activate.json", data=b"", headers=tmp_headers)
        if r.status_code == 200:
            tmp_headers["x-guest-token"] = r.json()["guest_token"]

        # the ct0 value is just a random 32-character string generated from random bytes at client side
        tmp_session.cookies.set("ct0", genct0())
        # set the headers accordingly
        tmp_headers["x-csrf-token"] = tmp_session.cookies.get("ct0")

        tmp_headers["Content-Type"] = "application/json"
        tmp_headers["Host"] = "twitter.com"

        return tmp_session, tmp_headers

    @staticmethod
    def _user_from_result(result):
        """
        Extract the user profile from the result dictionary.
        """
        if result is None:
            return "does_not_exist", None

        user = result.legacy

        if result.__typename == "User":
            p = TwitterUserProfile(
                int(result.rest_id),
                user.screen_name,
                created_at=user.created_at,
                following_count=user.friends_count,
                followers_count=user.followers_count,
                tweet_count=user.statuses_count,
                media_count=user.media_count,
                favourites_count=user.favourites_count,
                display_name=user.name,
            )
            if result.legacy.profile_interstitial_type == "fake_account":
                return "fake_account", p
            if result.legacy.protected:
                return "protected", p
            return "normal", p

        if result.__typename == "UserUnavailable":
            if "suspends" in result.unavailable_message.text:
                return "suspended", None

    @staticmethod
    def user_by_screen_name(screen_name):
        """
        Returns the account status and the user profile, given user's screen_name.
        """
        tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        display_msg("get user by screen name")

        url = TwitterBot.urls["user_by_screen_name"]
        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"] = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        form["features"]["blue_business_profile_image_shape_enabled"] = False

        encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})
        r = tmp_session.get(url, headers=tmp_headers, params=encoded_params)

        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            return TwitterBot._user_from_result(response.data.user.result)
        else:
            print(r.status_code, r.text)

    @staticmethod
    def user_by_id(user_id):
        """
        Returns the account status and the user profile, given user's id.
        """
        tmp_session, tmp_headers = TwitterBot.tmp_session_headers()

        display_msg("get user by rest id")

        url = TwitterBot.urls["user_by_rest_id"]
        form = copy.deepcopy(TwitterBot.tweet_replies_form)

        form["variables"] = {"userId": str(user_id), "withSafetyModeUserFields": True}

        encoded_params = urlencode({k: json.dumps(form[k], separators=(",", ":")) for k in form})

        r = tmp_session.get(url, headers=tmp_headers, params=encoded_params)

        if r.status_code == 200:
            response = r.json()
            response = TwitterJSON(response)
            return TwitterBot._user_from_result(response.data.user.result)
        else:
            print(r.status_code, r.text)

    @staticmethod
    def status_by_screen_name(screen_name):
        """
        Probe the status of an account, given user's screen_name.
        """
        values = TwitterBot.user_by_screen_name(screen_name)
        if values:
            status, user_profile = values
            return status

    @staticmethod
    def status_by_id(user_id):
        """
        Probe the status of an account, given user's id.
        """
        values = TwitterBot.user_by_id(user_id)
        if values:
            status, user_profile = values
            return status


if __name__ == "__main__":
    pass
