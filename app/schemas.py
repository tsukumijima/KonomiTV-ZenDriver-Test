# ruff: noqa: RUF012

# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ***** Twitter 連携 *****


class Tweet(BaseModel):
    id: str
    created_at: datetime
    user: TweetUser
    text: str
    lang: str
    via: str
    image_urls: list[str] | None
    movie_url: str | None
    retweet_count: int
    retweeted: bool
    favorite_count: int
    favorited: bool
    retweeted_tweet: Tweet | None
    quoted_tweet: Tweet | None


class TweetUser(BaseModel):
    id: str
    name: str
    screen_name: str
    icon_url: str


class TwitterAPIResult(BaseModel):
    is_success: bool
    detail: str


class PostTweetResult(TwitterAPIResult):
    tweet_url: str


class TimelineTweetsResult(TwitterAPIResult):
    next_cursor_id: str
    previous_cursor_id: str
    tweets: list[Tweet]
