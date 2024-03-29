import matplotlib.pyplot as plt
import numpy as np

import yaml
import traceback
from datetime import datetime, timezone
import re

import pytz
from PIL import Image

def display_msg(msg):
    print(f"\n{msg:.>50}")

def image_file_type(filename):
    image = Image.open(filename)
    image_type = image.format
    return image_type

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

def snowflake_id_to_unix_timestamp(tweet_id):
    """
    Convert twitter snowflake id to **********.*** unix timestamp
    """
    offset = 1288834974657
    tstamp = (tweet_id >> 22) + offset
    return tstamp/1000

def queryID_from_url(url):
    return url.split("/")[-2].strip()

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

def hour_hist_from_timestamps(timestamps):
    """
    Returns:

    a 24-element list that counts occurences of each hour in the utc timestamps. 
    """
    SECONDS_PER_HOUR = 3600
    SECONDS_PER_DAY = SECONDS_PER_HOUR * 24
    hours = [x % SECONDS_PER_DAY // SECONDS_PER_HOUR for x in timestamps]
    hist = [0]*24
    for x in hours:
        hist[x]+=1
    return hist

def weekday_hist_from_timestamps(timestamps, utc_offset = None, tz = None):
    weekdays = [get_weekday(x, utc_offset = utc_offset, tz=tz) for x in timestamps]
    hist = [0]*7
    for x in weekdays:
        hist[x]+=1
    return hist

def plot_utc_timestamps_by_hour(timestamps):
    """
    Plot the hourly histogram of the timestamps.
    The timestamps are in utc timestamp format.
    """
    hourly = hour_hist_from_timestamps(timestamps)
    # Create bar plot
    plt.bar(range(24),hourly)
    #plt.hist(hours, bins=[x for x in range(25)], density=True)
    #plt.xlim([0, 24])
    plt.xlabel("hour (UTC+00:00)")
    plt.ylabel("count")
    plt.title("posting time")
    plt.show()


def plot_utc_timestamps_intervals(timestamps, minimum=None, maximum=None):
    post = np.array(timestamps[1:])
    pre = np.array(timestamps[:-1])
    intervals = pre - post

    if minimum is not None and maximum is not None:
        intervals = [x for x in intervals if x > minimum and x < maximum]

    plt.hist(intervals)
    plt.show()
