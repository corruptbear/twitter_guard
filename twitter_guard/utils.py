
import yaml
import traceback
from datetime import datetime, timezone
import re

import pytz

def display_msg(msg):
    print(f"\n{msg:.>50}")


def save_yaml(dictionary, filepath, write_mode):
    try:
        with open(filepath, write_mode) as f:
            yaml.dump(dictionary, f)
    except:
        traceback.print_exc()

def load_yaml(filepath):
    """
    Load the yaml file. Returns an empty dictionary if the file cannot be read.
    """
    # yaml_path = os.path.join(pwd, filepath)
    try:
        with open(filepath, "r") as stream:
            dictionary = yaml.safe_load(stream)
            return dictionary
    except:
        traceback.print_exc()
        return dict()


# the post timestamp and user.created timestamp have inconsistent format
def sns_timestamp_to_utc_datetime(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=timezone.utc)

def tweet_timestamp_to_utc_datetime(timestamp):
    return datetime.strptime(timestamp, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)

def tweet_timestamp_from_sns_timestamp(sns_timestamp):
    return sns_timestamp_to_utc_datetime(sns_timestamp).strftime("%a %b %d %H:%M:%S +0000 %Y")

def sns_timestamp_from_tweet_timestamp(tweet_timestamp):
    return tweet_timestamp_to_utc_datetime(tweet_timestamp).replace(tzinfo=timezone.utc).isoformat()
 
def get_tznames(timestamp, offset_hours):
    """
    get the names of timezones that at the time of the timestamp, have a time difference from GMT 00:00 as specified.

    Parameters:
    timestamp : could be an integer utctimestamp, or a datetime object.
    offset_hours: could be integer or non-integer.

    Returns:
    list: a list of timezones with the given offset
    """
    #use mod to convert negative offset to positive ones used by the library
    offset_seconds = int(3600 * offset_hours)%(3600*24) 
    if not isinstance(timestamp, datetime):
        if isinstance(timestamp,int):
            timestamp = datetime.utcfromtimestamp(timestamp) 

    return [x for x in pytz.common_timezones if pytz.timezone(x).utcoffset(timestamp).seconds == offset_seconds]

def get_weekday(timestamp, utc_offset = None, tz = None):
    """
    get the weekday at the specified time and timezone.

    Parameters:
    timestamp : could be an integer utctimestamp, or a datetime object.
    utc_offset: could be integer or non-integer.

    Returns:
    weekday (int): the weekday, using a coding scheme that starts from 0: Monday = 0, Tuesday = 1, ... and so on.
    """
    if tz is None:
        specific_tz = pytz.timezone(get_tznames(timestamp, utc_offset)[0])
    else:
        specific_tz = pytz.timezone(tz)
    if not isinstance(timestamp, datetime):
        timestamp = datetime.utcfromtimestamp(timestamp)
    weekday = timestamp.replace(tzinfo=timezone.utc).astimezone(specific_tz).weekday()
    return weekday


def get_source_label(s):
    """
    Parses the source field and get the label
    """
    #s = '<a href="http://twitter.com/download/iphone" rel="nofollow">Twitter for iPhone</a>'
    match = re.search(r">(.*)</a>", s)
    return match.group(1)
