import matplotlib.pyplot as plt
import numpy as np

import yaml
import traceback
from datetime import datetime, timezone
import snscrape.modules.twitter as sntwitter

def display_msg(msg):
    print(f"\n{msg:.>50}")

def save_yaml(dictionary, filepath, write_mode):
    with open(filepath, write_mode) as f:
        yaml.dump(dictionary, f)


def load_yaml(filepath):
    # yaml_path = os.path.join(pwd, filepath)
    try:
        with open(filepath, "r") as stream:
            dictionary = yaml.safe_load(stream)
            return dictionary
    except:
        traceback.print_exc()
        return None
        
def sns_timestamp_to_utc_datetime(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=timezone.utc)
    
def tweet_timestamp_to_utc_datetime(timestamp):
    return datetime.strptime(timestamp, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)

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
    
def plot_utc_timestamps_by_hour(timestamps):
    """
    The timestamps are in utc timestamp format.
    """
    SECONDS_PER_HOUR = 3600
    SECONDS_PER_DAY = SECONDS_PER_HOUR*24
    hours = [x%SECONDS_PER_DAY//SECONDS_PER_HOUR for x in timestamps]

    # Create bar plot
    plt.hist(hours,bins=[x for x in range(25)],density=True)
    plt.xlim([0,24])
    plt.xlabel('hour (utc)')
    plt.title('posting time')
    plt.show()
    
def plot_utc_timestamps_intervals(timestamps, minimum = None, maximum = None):
    post = np.array(timestamps[1:])
    pre = np.array(timestamps[:-1])
    intervals = pre - post
    
    if minimum is not None and maximum is not None:
        intervals = [x for x in intervals if x>minimum and x<maximum]
    
    plt.hist(intervals)
    plt.show()
