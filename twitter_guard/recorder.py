import os
import json
import sqlite3
from .utils import *
from .apifree_bot import TwitterBot

class Recorder:
    def __init__(self, db_path):
        self.db_path = db_path
        self._create_db()

    def _create_table(self, create_table_sql):
        try:
            self._cursor.execute(create_table_sql)
        except Exception as e:
            print(e)

    def _create_db(self):
        """
        Connet to the database.
        Initialize the connection and the cursor.
        Create tables if not exist.
        """
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._cursor = self.conn.cursor()

        create_queries_table_sql = """
        CREATE TABLE IF NOT EXISTS queries
        (query text, latest_result_date text)
        """

        create_users_table_sql = """
        CREATE TABLE IF NOT EXISTS users
        (user_id int PRIMARY KEY, screen_name text, created_at text, following_count integer, followers_count integer, tweet_count integer, favourites_count integer, media_count integer, last_seen_post_id integer, account_status text DEFAULT 'normal')
        WITHOUT ROWID
        """

        create_posts_table_sql = """
        CREATE TABLE IF NOT EXISTS posts
        (post_id int PRIMARY KEY, account_id integer, created_at text, source text, reply_count integer, retweet_count integer, like_count integer, quote_count integer, view_count integer, query text, content text)
        WITHOUT ROWID
        """

        self._create_table(create_queries_table_sql)
        self._create_table(create_users_table_sql)
        self._create_table(create_posts_table_sql)

        add_users_column_sql = """
        ALTER TABLE users
        ADD COLUMN account_status text DEFAULT 'normal'
        """

        drop_suspended_column_sql = """
        ALTER TABLE users
        DROP COLUMN suspended
        """

        # self._cursor.execute(drop_suspended_column_sql)

    def record(self, query):
        """
        Collect results incrementally
        """
        results = TwitterBot.search_timeline(query)

        self._cursor.execute("SELECT rowid, latest_result_date from queries WHERE query = (?)", (query,))
        self.conn.commit()

        query_record = self._cursor.fetchall()

        # if the query is not new, get the timestamp for the latest post previously seen
        if len(query_record) != 0:
            latest_result_date = query_record[0][1]
        else:
            latest_result_date = "1970-01-01T00:00:00+00:00"
            self._cursor.execute("INSERT INTO queries VALUES (?,?)", (query, "1970-01-01T00:00:00+00:00"))
            

        recorded_latest_timestamp = sns_timestamp_to_utc_datetime(latest_result_date) #2023-04-16T01:19:29+00:00

        count = 0
        for tweet in results:
            # print(content)
            user = tweet.user
            user_id = int(user.user_id)
            screen_name = user.screen_name
            created_at = user.created_at
            following_count = user.following_count
            followers_count = user.followers_count
            tweet_count = user.tweet_count
            favourites_count = user.favourites_count
            media_count = user.media_count

            # tweet information
            text_raw = tweet.text
            post_id = tweet.tweet_id
            posted_at = tweet.created_at
            source = tweet.source

            if get_source_label(source) != "Twitter Web App":
                print(f"{source:.>100}")

            timestamp = sns_timestamp_to_utc_datetime(posted_at)
            # if latest post in the current search
            if count == 0:
                # update the table if unseen
                if timestamp > recorded_latest_timestamp:
                    print("new data seen!")
                    self._cursor.execute("UPDATE queries SET latest_result_date=? WHERE query=?", (posted_at, query))

            # compare the current timestamp with the recorded latest timestamp
            if timestamp <= recorded_latest_timestamp:
                print(f"counter: {count}, reaches the point of last search")
                break

            print(f"counter: {count:<6} timestamp: {posted_at:<25} user:{screen_name:<16} text: {text_raw}")

            # tweet statistics
            if tweet.view_count is not None:
                view_count = tweet.view_count
            else:
                view_count = None
            reply_count = tweet.reply_count
            retweet_count = tweet.retweet_count
            like_count = tweet.favorite_count
            quote_count = tweet.quote_count

            # related entities
            # retweeted_tweet = content["retweetedTweet"]
            # quoted_tweet = content["quotedTweet"]
            # in_reply_to_tweet_id = content["inReplyToTweetId"]
            # in_reply_to_user = content["inReplyToUser"]
            self._cursor.execute(
                "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id,
                    screen_name,
                    created_at,
                    following_count,
                    followers_count,
                    tweet_count,
                    favourites_count,
                    media_count,
                    post_id,
                    "normal",
                ),
            )

            self._cursor.execute(
                "UPDATE posts SET reply_count=?, retweet_count=?, like_count=?, quote_count=?, view_count=? WHERE post_id=?",
                (reply_count, retweet_count, like_count, quote_count, view_count, post_id),
            )
            self._cursor.execute(
                "INSERT OR IGNORE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    post_id,
                    user_id,
                    posted_at,
                    source,
                    reply_count,
                    retweet_count,
                    like_count,
                    quote_count,
                    view_count,
                    query,
                    text_raw,
                ),
            )
            self.conn.commit()

            count += 1

    def delete_user(self, screen_name):
        # delete associated posts first
        account_id = id_from_screen_name(screen_name)
        self._cursor.execute(
            "DELETE from posts where account_id in (SELECT account_id FROM posts JOIN users ON (posts.account_id=users.user_id) WHERE users.screen_name=?)",
            (screen_name,),
        )
        # self._cursor.execute("DELETE from posts where account_id=?",(account_id,))
        # then delete from the users table
        self._cursor.execute("DELETE from users where screen_name=?", (screen_name,))

        print(f"{screen_name} deleted from the tables!")
        self.conn.commit()

    def show_suspended_users(self):
        # all suspended
        self._cursor.execute(
            "SELECT users.screen_name, users.tweet_count, users.created_at as user_created_at, posts.created_at as last_seen_at FROM posts JOIN users ON (posts.post_id = users.last_seen_post_id) WHERE users.account_status='suspended' ORDER BY posts.created_at"
        )
        for x in self._cursor.fetchall():
            print(dict(x))

    def check(self):
        self._cursor.execute("SELECT * from queries")
        for x in self._cursor.fetchall():
            print(dict(x))

        self._cursor.execute("SELECT * from users ORDER BY screen_name")
        for x in self._cursor.fetchall():
            print(dict(x))

        # self._cursor.execute("SELECT * FROM posts")
        # self._cursor.execute("SELECT * FROM posts WHERE created_at BETWEEN '2023-01-01' AND '2023-03-01'")
        # self._cursor.execute("SELECT * FROM posts JOIN users ON (posts.account_id=users.user_id) WHERE source NOT LIKE '%Twitter Web App%' AND users.account_status!='suspended'")
        # self._cursor.execute("SELECT posts.post_id, posts.created_at as post_created_at, posts.source, posts.content as post_content, users.screen_name, users.user_id, users.created_at as user_created_at, users.account_status FROM posts JOIN users ON (posts.account_id=users.user_id) WHERE source LIKE '%easestrategy%'")
        # for x in self._cursor.fetchall():
        #    print(dict(x))

    def show_tweets_by_screen_name(self, screen_name):
        display_msg("check_tweets")
        self._cursor.execute(
            "SELECT users.user_id, users.screen_name, posts.created_at as post_created_at,  posts.source, posts.content FROM (users JOIN posts ON users.user_id = posts.account_id) WHERE users.screen_name=? ORDER BY posts.created_at",
            (screen_name,),
        )
        for x in self._cursor.fetchall():
            print(dict(x))

    def check_status(self):
        display_msg("check status now")
        self._cursor.execute("SELECT COUNT(*) from users")
        for x in self._cursor.fetchall():
            print("all users:", dict(x))
        self._cursor.execute("SELECT COUNT(*) from users WHERE users.account_status='suspended'")
        for x in self._cursor.fetchall():
            print("suspended users:", dict(x))
        self._cursor.execute("SELECT COUNT(*) from posts")
        for x in self._cursor.fetchall():
            print("all posts:", dict(x))

        # self._cursor.execute(
        #    "UPDATE users SET account_status='suspended' WHERE users.suspended=1"
        # )
        # self.conn.commit()

        # examine the status of exiting accounts
        # self._cursor.execute("SELECT users.user_id, users.screen_name, posts.created_at FROM (users JOIN posts ON users.last_seen_post_id = posts.post_id) WHERE users.account_status!='suspended' ORDER BY posts.created_at")
        self._cursor.execute(
            "SELECT users.user_id, users.screen_name, posts.created_at as last_post_created_at, account_status FROM (users JOIN posts ON users.last_seen_post_id = posts.post_id)  WHERE (account_status!='suspended' and account_status!='does_not_exist') AND (posts.created_at>='2023-01-01') ORDER BY posts.created_at"
        )
        # self._cursor.execute("SELECT users.user_id, users.screen_name, users.created_at as user_created_at, posts.created_at as last_post_created_at, posts.source as initially_recorded_source, users.suspended as account_suspended FROM (users JOIN posts ON users.last_seen_post_id = posts.post_id) WHERE (((posts.source LIKE '%easestrategy%') OR (posts.source LIKE '%Ruyitie%'))) ORDER BY posts.created_at")
        for user in self._cursor.fetchall():
            user_dict = dict(user)
            user_id = user_dict["user_id"]
            screen_name = user_dict["screen_name"]
            last_posted = user_dict["last_post_created_at"]
            # source = user_dict['initially_recorded_source']
            old_status = user_dict["account_status"]
            new_status = TwitterBot.status_by_id(int(user_id))
            print(f"{user_id:<20} {screen_name:<16} {last_posted} {old_status} -> {new_status}")
            # print(user_dict)

            if new_status is not None:
                self._cursor.execute("UPDATE users SET account_status=? WHERE user_id=?", (new_status, user_id))
                self.conn.commit()
