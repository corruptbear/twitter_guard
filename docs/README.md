# twitter_guard

## Introduction

A Python package for defending against harassment on Twitter.

## Supported Python Versions

**Python 3.9+**


## Installation

Install directly from github
```bash
#if you are using python3.9, for example
python3.9 -m pip install --user git+https://github.com/wsluo/twitter_guard
```  

## Configuration
To use the package, create `apifree.yaml`, `white_list.yaml` and `block_list.yaml` in the folder where your own script resides.

`apifree.yaml`

Before first time use,  set `latest_cursor` field as `""`.
```yaml
filtering_rule: your_custom_filtering_rule
latest_cursor: "" 
login:
  email: your_actual_stuff_here
  password: your_actual_stuff_here
  phonenumber: your_actual_stuff_here
  screenname: your_actual_stuff_here
```

put known friends in `white_list.yaml` line by line
```yaml
id1_of_your_friend: name1_of_your_friend
id2_of_your_friend: name2_of_your_friend
```

put known friends in `block_list.yaml` line by line
```yaml
id1_of_your_enemy: name1_of_your_enemy
id2_of_your_enemy: name2_of_your_enemy
```

## Quick Examples

### check the notification tab and block bad users.
```python
import os
from twitter_guard.apifree_bot import TwitterBot

#specify the paths of configs and cookies
pwd = os.path.dirname(os.path.realpath(__file__))
COOKIE_PATH = os.path.join(pwd, "sl_cookies.pkl")
CONFIG_PATH = os.path.join(pwd, "apifree.yaml")
WHITE_LIST_PATH = os.path.join(pwd, "white_list.yaml")
BLOCK_LIST_PATH = os.path.join(pwd, "block_list.yaml")

#create the bot
bot = TwitterBot(
    cookie_path=COOKIE_PATH,
    config_path=CONFIG_PATH,
    white_list_path=WHITE_LIST_PATH,
    block_list_path=BLOCK_LIST_PATH,
)

try:
    # use a small query to test the validity of cookies
    bot.get_badge_count()
except:
    bot.refresh_cookies()

#examing recent interactions, and block users according to the filtering_rule defined in apifree.yaml
bot.check_notifications(block=True)
```

### filtering rule
logic expression describing bad accounts

- logic operators:  `not` `and` `or`  
- arithmatic operators: `+` `-` `*` `/`
- comparison operators:  `>` `<` `>=` `<=` `==` `!=`
- keywords: `followers_count ` `following_count`  `tweet_count` `media_count` `favourites_count` `days`  

Example
```
"(followers_count <= 5 and following_count <= 5) or (days <= 180)"
"(followers_count <= 10 and following_count <= 10) or (days <= 360) or ((followers_count/(tweet_count + 1) > 20) and tweet_count < 100)"
```