import matplotlib.pyplot as plt
import numpy as np

import yaml
import traceback
from datetime import datetime, timezone
import snscrape.modules.twitter as sntwitter
import re

def display_msg(msg):
    print(f"\n{msg:.>50}")


def save_yaml(dictionary, filepath, write_mode):
    with open(filepath, write_mode) as f:
        yaml.dump(dictionary, f)


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


def get_source_label(s):
    #s = '<a href="http://twitter.com/download/iphone" rel="nofollow">Twitter for iPhone</a>'
    match = re.search(r">(.*)</a>", s)
    return match.group(1)

def id_from_screen_name(screen_name):
    """
    Gets the numerical user id given the user handle.
    """
    x = sntwitter.TwitterUserScraper(screen_name)
    userdata = x._get_entity()
    return int(userdata.id)


def numerical_id(user_id):
    try:
        int_user_id = int(user_id)
    except:
        int_user_id = id_from_screen_name(user_id)

    return int_user_id

def hourly_from_timestamps(timestamps):
    SECONDS_PER_HOUR = 3600
    SECONDS_PER_DAY = SECONDS_PER_HOUR * 24
    hours = [x % SECONDS_PER_DAY // SECONDS_PER_HOUR for x in timestamps]
    hourly = [0]*24
    for x in hours:
        hourly[x]+=1
    return hourly

def plot_utc_timestamps_by_hour(timestamps):
    """
    Plot the hourly histogram of the timestamps.
    The timestamps are in utc timestamp format.
    """
    hourly = hourly_from_timestamps(timestamps)
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
