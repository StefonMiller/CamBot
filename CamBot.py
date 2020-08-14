import calendar
import json
import math
import os
import random
import re
import urllib
from time import strftime, gmtime, time
import discord
import requests
from steam_community_market import Market, AppID
from requests import get
from contextlib import closing
from bs4 import BeautifulSoup
import tweepy
from datetime import datetime, date, timedelta, time
from fuzzywuzzy import fuzz
import asyncio
import pyotp
from tweepy import TweepError
from timeit import default_timer as timer
import skinml
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import sqlite3
import updater as cambot_updater
import steamwebapi
updated_devblog = False


class PriceSkin:
    def __init__(self, name, link, init_price, release_date, curr_price, img):
        self.n = name
        self.l = link
        self.ip = init_price
        self.rd = release_date
        self.cp = curr_price
        self.pc = "{:.2f}".format(((float(self.cp) - self.ip) / self.ip) * 100)
        self.img = img

    def get_name(self):
        return self.n

    def get_link(self):
        return self.l

    def get_init_price(self):
        return self.ip

    def get_release_date(self):
        return self.rd

    def get_curr_price(self):
        return self.cp


class Skin:
    def __init__(self, name, price, type, predicted_price, img_url):
        self.n = name
        self.p = price
        self.t = type
        self.pr = predicted_price
        self.im = img_url

    def get_name(self):
        return self.n

    def get_price(self):
        return self.p

    def get_type(self):
        return self.t

    def get_predicted_price(self):
        return self.pr

    def get_img_url(self):
        return self.im


# Get API keys from keys text file
with open('keys.txt') as f:
    keys = f.read().splitlines()
    f.close()
# Create client object for discord integration
client = discord.Client()

# Connect to the SQLite database
connection = None
try:
    connection = sqlite3.connect('rustdata.db')
    cursor = connection.cursor()
except Exception as e:
    print(e)
finally:
    if connection:
        print('Successfully connected to SQLite database')


# Background task used to check for website changes
async def check():
    global updated_devblog
    await client.wait_until_ready()
    while not client.is_closed():
        print('Checking for site changes...')
        # Get the first skin in the rust item store to check for changes
        check_item_html = get_html('https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        # If we get an exeception when attempting to connect to the Rust site, don't bother checking for updates as
        # the site is down
        try:
            check_item = check_item_html.find('div', {"class": "item_def_name ellipsis"}).find('a').text
        except Exception:
            print('Rust item store is currently down')
            check_item = None

        # Get the title of the newest article on rustafied to check for changes
        news_title, news_desc = get_news('https://rustafied.com')

        # Get the title of the newest devblog to check for updates
        devblog_title, devblog_url, desc = get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')

        # Only check for rust item updates if we get items from the item store. If no items were returned, then
        # the store is currently updating or is having issues
        if check_item:
            item_status = check_for_updates('C:/Users/Stefon/PycharmProjects/CamBot/current_skins.txt', check_item)
        else:
            item_status = 0
        # Check if any of the corresponding text files were updated
        news_status = check_for_updates('C:/Users/Stefon/PycharmProjects/CamBot/current_news.txt', news_title)
        devblog_status = check_for_updates('C:/Users/Stefon/PycharmProjects/CamBot/current_devblog.txt', devblog_title)

        # If any of the files were updated, get the channels to post in. This avoids finding all appropriate channels
        # when we don't need to
        if item_status == 1 or news_status == 1 or devblog_status == 1:

            # Loop through all servers Cambot is connected to. For each server get the first text channel to post the
            # update(s) to. However, if there is a text channel called 'Squaddies' then use that instead
            channel_list = []
            for guild in client.guilds:
                first_channel = None
                for channel in guild.channels:
                    if not first_channel:
                        first_channel = channel
                    elif channel.name.lower() == 'squaddies':
                        first_channel = channel
                    else:
                        pass
                if first_channel:
                    channel_list.append(first_channel)

            if item_status == 1:
                items, total_item_price = get_rust_items(
                    'https://store.steampowered.com/itemstore/252490/browse/?filter=All')
                await update_items(channel_list, items, total_item_price)
                print('Posted item store update')
            if news_status == 1:
                await post_rust_news_update(channel_list, news_title, news_desc)
                print('Posted Rustafied news update')
            if devblog_status == 1:
                await post_devblog_update(channel_list, devblog_title, devblog_url, desc)
                print('Posted devblog update')
                updated_devblog = True
        else:
            print('No changes found...')
            pass
        sleep_timer = 900
        # Check if it is the first thursday of the month. If it is, then check if the flag for updating the
        # devblog has been set to true. If it hasn't, then we can set the sleep_timer to 60 until we update the
        # Devblog which will set the flag to true. Then, if the day is not the first thursday of the month, we will
        # set the flag back to false
        if check_day():
            print('It is the first thursday of the month')
            if not updated_devblog:
                print('Devblog not updated, checking if wipe is close')
                sleep_timer = check_time()
        else:
            print('Not first thursday of the month, keeping sleep timer the same')
            updated_devblog = False

        await asyncio.sleep(sleep_timer)


# Checks if we are within 1 hour of normal wipe time and returns a sleep time corresponding to the answer
def check_time():
    wipe_time = datetime.strptime('14:00:00', "%H:%M:%S")
    current_time = datetime.now()
    difference = wipe_time - current_time

    # If there is more than 1 hour + the max sleep time before wipe
    if (difference.seconds / 60) > 60:
        print('Wipe is not close enough...')
        return 900
    else:
        print('Wipe is close...')
        return 60


# Checks if it is the first thrusday of the month and returns true if it is
def check_day():
    nth = 1
    if date(date.today().year, date.today().month, 1).weekday() == 3:
        nth = nth - 1
    return date.today() == calendar.Calendar(3).monthdatescalendar(date.today().year, date.today().month)[nth][0]


# Returns the player count of a certain server URL on Battlemetrics.com
# @Param server_url: - url of the server we want the player count of
# @Return: - number of players on the server
def server_pop(server_url):
    server_html = get_html(server_url)
    pop = server_html.find('dt', string='Player count').find_next_sibling('dd')
    return pop.text


# Inserts all current items from the rust store into the MySQL server and the local text file of item names
def insert_items(items):
    # Get current date
    today = date.today()
    # For each item in the dictionary, convert the name to a steam market url and insert the item's data into
    # the MySQL server
    for item in items:
        item_name = item.get_name()
        item_price = item.get_price()
        item_type_url = item.get_type()
        item_http = item_name.replace(' ', '%20')
        item_http = item_http.replace('&', '%26')
        item_http = item_http.replace('?', '%3F')
        item_url = 'https://steamcommunity.com/market/listings/' + '252490' + '/' + item_http
        item_img = item.get_img_url()
        item_price = float(item_price[1:])
        try:
            item_type_html = get_html(item_type_url)
            item_type = item_type_html.find('span', {"style": "color: #ffdba5"})
            if item_type is None:
                item_type = 'LR-300'
            else:
                item_type = item_type.text
            sql = "INSERT INTO skin (skin_name, link, initial_price, release_date, skin_type, skin_img)" \
                  " VALUES(?, ?, ?, ?, ?, ?)"
            val = (item_name, item_url, item_price, today, item_type, item_img)
            cursor.execute(sql, val)
            connection.commit()
            print('Successfully inserted ' + item_name)
            # Once we insert the items, we know it is not a duplicate entry and can insert the name into our text file
            # containing all skin names
            with open('C:/Users/Stefon/PycharmProjects/CamBot/skins.txt', "a") as file:
                file.write(item_name + '\n')
                print('Added ' + item_name + ' to text file')
        except Exception as e:
            print('Duplicate entry, skipping ' + item_name + '...' + str(e))

    return


# Announces the rust item store has updated, displays all item data, and then calls insert_items
# @Param channels: List of channels to post the announcement to
# @Param items: all items currently in the store
# @Param total_price: Total price of all items
async def update_items(channels, items, total_price):
    # If the list is empty, then the item store is having an error or is updating
    if not bool(items):
        pass
    # If we have entries, format and display them
    else:
        # Display the first item we get in an embed
        embed = discord.Embed(title=items[0].n,
                              url='https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        embed.set_thumbnail(url=items[0].im)
        footer_text = 'Page 1/' + str(len(items))
        embed.set_footer(text=footer_text)
        embed.add_field(name='Item price', value=items[0].p, inline=True)
        price = items[0].pr
        embed.add_field(name='Predicted price(1yr)', value=price, inline=True)
        for channel in channels:
            await channel.send('The Rust item store has updated with new items')
            msg = await channel.send(embed=embed)
            # Insert all other items into the SQL database with corresponding message and channel ids
            for item in items:
                try:
                    sql = "INSERT INTO item_store_messages (message_id, channel_id, item_name, starting_price, " \
                          "predicted_price, store_url) VALUES(?, ?, ?, ?, ?, ?)"
                    temp_pr = str(item.pr)
                    val = (msg.id, channel.id, item.n, item.p, temp_pr, item.im)
                    cursor.execute(sql, val)
                    connection.commit()
                    print('Successfully inserted ' + item.n)
                except Exception as e:
                    print('Error, skipping ' + item.n + '...' + str(e))
            # React to the message to set up navigation
            await msg.add_reaction('◀')
            await msg.add_reaction('▶')
    # Send out a tweet when the item store updates
    tweet('The Rust item store has updated with new items: https://store.steampowered.com/itemstore/252490/'
          'browse/?filter=All')

    insert_items(items)
    return


# Make a post in channel announcing the new devblog
# @Param channels: List of channels to post the announcement to
# @Param title: Title of devblog
# @Param url: URL of devblog
# @Param desc: description of devblog
async def post_devblog_update(channels, title, url, desc):
    embed = discord.Embed(title=title, url=url, description=desc)
    for channel in channels:
        await channel.send('A new Rust devblog has been uploaded:', embed=embed)
    tweet('A new Rust devblog has been uploaded: ' + url)
    return


# Make a post in channel announcing the new rust news on Rustafied
# @Param channels: List of channels to post the announcement to
# @Param title: Title of news article
# @Param desc: Description of news article
async def post_rust_news_update(channels, title, desc):
    embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
    for channel in channels:
        await channel.send('Rustafied has published a new news article', embed=embed)
    tweet('Rustafied has published a news article https://rustafied.com')
    return


# Check a website for changes
# @Param current_path: Path to text file containing data taken from most recent update check
# @Param current_data: Data pulled from the website at the time of calling the method
# @Return 1 or 0 depending on if the file needs updated
def check_for_updates(current_path, current_data):
    # Open the text file and get the most recent data
    with open(current_path) as file:
        check_name = file.read().splitlines()
        file.close()
    # If there is no data in the text file it needs to be updated
    if not check_name:
        with open(current_path, 'w') as f:
            f.write(current_data)
            f.close()
        return 1
    # If the names match, then the list is up to date
    elif check_name[0] == current_data:
        return 0
    # If the names do not match, then the file needs to be updated
    else:
        with open(current_path, 'w') as f:
            f.write(current_data)
            f.close()
        return 1


# Gets the status of all servers the CamBot is dependent on
# @Return: List of servers and connection stats
def get_status():
    # Fill an array with each server we want to test
    import requests
    server_names = ['https://www.battlemetrics.com', 'https://rust.facepunch.com/blog/', 'https://www.rustlabs.com/',
                    'https://rustafied.com/']

    server_dict = {}
    for server in server_names:
        connection_status = requests.head(server)
        if connection_status.status_code == 200 or 301:
            server_dict[server] = '🟢 Online'
        else:
            server_dict[server] = '🔴 Offline'
    return server_dict


# Formats a dictory of name/value embeds along with thumbnail/url data
# @Param fields: Dictionary of fields with each embed name being the key and the embed value being the value
# @Param title: Title of the embed
# @Param title_url: Hyperlink URL for the embed title
# @Param description: Description of the embed
# @Param thumbnail: Thumbnail of the embed.
# @Param footer: Footer of the embed
# @return: Embed formatted for the number of items in fields
def format_embed(fields=None, title=None, title_url=None, description=None, thumbnail=None, footer=None):
    embed = discord.Embed(title=title, description=description, url=title_url)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if footer:
        embed.set_footer(text=footer)
    if fields:
        num_fields = len(fields)
        num_rows = num_fields // 3
        remaining_fields = num_fields % 3
        names = list(fields.keys())
        if remaining_fields == 0 or num_fields > 8:
            for i in range(num_rows):
                # For each row that is divisible by 3, add 3 fields corresponding to that row
                embed.add_field(name=names[(i * 3)], value=fields[names[(i * 3)]], inline=True)
                embed.add_field(name=names[(i * 3) + 1], value=fields[names[(i * 3) + 1]], inline=True)
                embed.add_field(name=names[(i * 3) + 2], value=fields[names[(i * 3) + 2]], inline=True)
            if remaining_fields == 2:
                embed.add_field(name=names[-2], value=fields[names[-2]], inline=True)
                embed.add_field(name=names[-1], value=fields[names[-1]], inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
            elif remaining_fields == 1:
                embed.add_field(name=names[-1], value=fields[names[-1]], inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
        else:
            num_rows = num_fields // 2
            remaining_fields = num_fields % 2
            for i in range(num_rows):
                # For each row that is divisible by 3, add 3 fields corresponding to that row
                embed.add_field(name=names[(i * 2)], value=fields[names[(i * 2)]], inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
                embed.add_field(name=names[(i * 2) + 1], value=fields[names[(i * 2) + 1]], inline=True)
            if remaining_fields == 1:
                embed.add_field(name=names[-1], value=fields[names[-1]], inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
                embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
    return embed


# Returns the best item in i_list matching term. Used for craftcalc and serverpop commands
# @Param i_list: list of items that have a text attirbute for comparison
# @Param term: search term entered
# @Param scorer: scoring method for fuzzywuzzy
# @Return: Best matching element in i_list
def get_best_match(i_list, term):
    # This could be done with fuzzywuzzy's process.extractOne module, but I could not get it to work with a different
    # scorer than WRatio.
    best_item_match = None
    best_item_match_num = 0
    for i in i_list:
        # Get an average of multiple fuzzywuzzy scorers to get a better match. Note w is not averaged as its score
        # Is the most valued out of the 5 scorers
        r = fuzz.ratio(term, i.text)
        s = fuzz.token_set_ratio(term, i.text)
        p = fuzz.partial_ratio(term, i.text)
        w = fuzz.WRatio(term, i.text)
        srt = fuzz.token_sort_ratio(term, i.text)
        temp_ratio = (r + s + p + srt) / 4 + w

        if temp_ratio > best_item_match_num:
            best_item_match = i
            best_item_match_num = temp_ratio
    return best_item_match


# Returns the best item in str_list matching search_term. Identical to get_best_match, but this is for SQL rows
# @Param str_list: list of rows for comparison
# @Param search_term: search term entered
# @Return: Best matching element in str_list
def get_string_best_match(str_list, search_term):
    # This could be done with fuzzywuzzy's process.extractOne module, but I could not get it to work with a different
    # scorer than WRatio.
    best_item_match = None
    best_item_match_num = 0
    for str in str_list:
        # Get an average of multiple fuzzywuzzy scorers to get a better match. Note w is not averaged as its score
        # Is the most valued out of the 5 scorers
        r = fuzz.ratio(search_term, str)
        s = fuzz.token_set_ratio(search_term, str)
        p = fuzz.partial_ratio(search_term, str)
        w = fuzz.WRatio(search_term, str)
        srt = fuzz.token_sort_ratio(search_term, str)
        temp_ratio = (r + s + p + srt) / 4 + w

        if temp_ratio > best_item_match_num:
            best_item_match = str
            best_item_match_num = temp_ratio
        else:
            pass
    return best_item_match


# Gets all skin data using Bitskins API
# @Return: A dictionary filled with skin data for every item
def get_skin_prices():
    # Open file containing API keys
    with open('C:/Users/Stefon/PycharmProjects/CamBot/bitskins_keys.txt') as f:
        lines = f.read().splitlines()
        f.close()
    # Use API keys to connect to the api and send a request for skin prices
    api_key = lines[0]
    secret = lines[1]
    my_secret = secret
    my_token = pyotp.TOTP(my_secret)
    r = requests.get(
        'https://bitskins.com/api/v1/get_all_item_prices/?api_key=' + api_key + '&code=' + my_token.now() + '&app_id=252490')
    data = r.json()
    # Get all price data from the request and fill a dictionary with it
    item_names = data['prices']
    item_dict = {}
    for name in item_names:
        item_dict[name['market_hash_name']] = name['price']
    return item_dict


# Tweets a dynamic tweet, depending on the specified image/text
# @Param msg: Text to tweet
# @Param pic: Optional picture to tweet
# @Return: Status of tweet submission
def tweet(msg, pic=None):
    # Authorize and connect to API with our API keys
    auth = tweepy.OAuthHandler(keys[1], keys[2])
    auth.set_access_token(keys[3], keys[4])
    api = tweepy.API(auth)

    # Verify the credentials
    try:
        api.verify_credentials()
    except:
        return 'Error during authentication'
    # If there is no picture, simply tweet the message. Otherwise tweet the pic and msg
    if pic is None:
        try:
            api.update_status(msg)
        except TweepError as e:
            pass
    else:
        media = api.media_upload(pic)
        tweet = msg
        api.update_status(status=tweet, media_ids=[media.media_id])

    # Return successful tweet creation with timestamp
    return 'New tweet created at ' + datetime.now().strftime("%m-%d-%Y %H:%M:%S") + ' EST'


# Gets certain update post based on 2 keywords. This may be used to fetch community updates and such in the future which
# is why I decided to modularize the function call
# @Param url: The url of the rss feed to scrape
# @Param kw1: First keyword to scrape based on
# @Param kw2: Second keyword to scrape based on
# @Return: The update name, link, and description
def get_devblog(db_url, kw1, kw2):
    with urllib.request.urlopen(db_url) as u:
        xml = BeautifulSoup(u, 'xml')
        titles = xml.find_all('title')
        for title in titles:
            # Find the first title that has kw1 but not kw2, in the case of devblogs, we are looking for
            # titles that contain 'update' but not 'community'. This provides all monthly updates that are not
            # community updates
            if title.find(text=re.compile(kw1)) and not title.find(text=re.compile(kw2)):
                # Once we find the newest update, get the link to the devblog and its description
                link = title.find_next_sibling('a10:link')
                desc = title.find_next_sibling('description')
                # For some reason the rss feed bundles an image source with the description, so we take all text
                # after the br tag as our description
                description = desc.text.split("<br/>", 1)[1]
                return str(title.text), link['href'], description
        # If we don't find a matching title, return a no devblog result
        return 'No Devblog found'


# Returns a title and description of the newest update article on rustafied.com
# @Param url: The url of rustafied's website
# @Return: The title and description of the article at url
def get_news(news_url):
    news_html = get_html(news_url)
    title_element = news_html.find('h1', {"class": "entry-title"})
    desc_element = news_html.find('p', {"style": "white-space:pre-wrap;"})
    return title_element.text, desc_element.text


# Returns all item entries on rust's steam store page and their total price
# @Param url: URL of the rust item store
# @Return: A collection of all items and the total price of said items
def get_rust_items(item_url):
    item_html = get_html(item_url)
    item_divs = item_html.find_all('div', {"class": "item_def_grid_item"})
    # Check if the items we are attempting to get data on are cached or not
    first_item_name = item_divs[0].find('div', {"class": "item_def_name ellipsis"}).text
    # Open the file containing the cached item data and get the first item name
    with open("C:/Users/Stefon/PycharmProjects/CamBot/cached_items.txt") as file:
        cache = file.read().splitlines()
        file.close()
    # Get the first item name from the cache. If cache is null, simply pass as our next if statement will check if it
    # is null
    try:
        f_name = cache[0].split(',')[0]
    except Exception as e:
        pass

    if not cache or (f_name != first_item_name):
        # If the data we are looking up is not cached, then look everything up and add it to the text file
        print('Items not cached...')
        with open("C:/Users/Stefon/PycharmProjects/CamBot/cached_items.txt", 'w') as f:
            item_list = []
            total_price = 0
            for i in item_divs:
                # Get div containing item name and store its text attribute
                item_name_div = i.find('div', {"class": "item_def_name ellipsis"})
                item_name = item_name_div.text
                item_type = i.find('a')['href']
                # Get div containing item price and store its text attribute
                item_price_div = i.find('div', {"class": "item_def_price"})
                # Convert the price to a double for addition and store it in the total price var
                item_price = "".join(i for i in item_price_div.text if 126 > ord(i) > 31)
                item_price_in_double = float(item_price[1:])
                total_price += item_price_in_double
                # Get the predicted price of the item using the skinML module
                predicted_price = '$' + str(skinml.get_predicted_price(item_type))
                # Get the url of the item's image
                img_html = get_html(item_type)
                img_src = img_html.find('img', {"class": "workshop_preview_image"})['src']
                img_src = img_src.replace('65f', '360f')
                item_list.append(Skin(item_name, item_price, item_type, predicted_price, img_src))
                temp_arr = [item_name, item_price, item_type, predicted_price, img_src]
                write_text = ','.join(temp_arr) + '\n'
                f.write(write_text)
            f.close()

        return item_list, total_price
    else:
        print('Data cached, skipping item regeneration...')
        # If the cached name is the same as the name we are looking up, then we do not need to scrape the item store
        item_list = []
        total_price = 0
        for line in cache:
            data = line.split(',')
            total_price += float(data[1].replace('$', ''))
            item_list.append(Skin(data[0], data[1], data[2], data[3], data[4]))
        return item_list, total_price


# Gets an item from the RustLabs item page with name closest matching item_name
# Will be used to fetch item stats, skins, recycle output, etc
# @Param item_name: The user's search terms
# @Return: The item closest matching the search terms
def get_item(item_name):
    # Navigate to the item page of Rustlabs and put all items(links) in a list
    item_html = get_html('https://rustlabs.com/group=itemlist')
    item_links = []
    # From the list of tr's, get their links and put them in a list
    for item in item_html.find_all('a', {"class": "pad"}):
        item_links.append(item)
    # Get the best matching link to our item_name and return it
    matching_item = get_best_match(item_links, item_name)
    return matching_item


# Gets a BeautifulSoup html object from a given url, and prints out an error if there was an error connecting
# @Param url: URL to scrape
# @Return BS4 object if the scrape was successful. Empty string if unsuccessful
def get_html(url):
    with closing(get(url, stream=True)) as resp:
        content_type = resp.headers['Content-Type'].lower()
        if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
            html = BeautifulSoup(resp.content, 'html.parser')
            return html
        else:
            return ''


# Gets all skins of a certain type
# @Param type: Type of skin to look up
# @Return: The category matching best matching type and the resulting skins of that category
def get_skins_of_type(skin_type):
    # Get the skin category closest to type
    with open('C:/Users/Stefon/PycharmProjects/CamBot/skin_types.txt') as file:
        skin_type_list = file.read().splitlines()
        file.close()
    best_skin = get_string_best_match(skin_type_list, skin_type)
    # Select all skins of that category
    sql = "SELECT skin_name, link, initial_price, release_date, skin_img FROM skin WHERE skin_type = \"" + \
          best_skin + "\""
    cursor.execute(sql)
    data = cursor.fetchall()
    # Return data for skins of that category and the category name
    return data, best_skin


# For an input amount of sulfur, display how many rockets, c4, etc you can craft
# @Param sulfur: How much sulfur the user has
# @Param guild: Guild the message was sent in to check for emotes
# @Return: A string containing how many of each explosive they can craft
def sulf_calc(sulfur, guild):
    # Check if the sulfur emote is in the server
    sulfur_emoji = check_emoji(guild.emojis, 'sulfur')
    # Initialize the embed with a title using the sulfur emote
    embed_title = 'With ' + str(sulfur) + str(sulfur_emoji) + ' you can craft:'
    embed = discord.Embed(title=embed_title)
    # Create a dict of all other explosives with their sulfur values
    explosive_dict = {'rocket': 1400, 'explosive 5.56 rifle ammo': 25, 'satchel charge': 480,
                      'timed explosive charge': 2200}
    for explosive in explosive_dict.keys():
        # Pad each embed 'row' with an empty field to get a 2-column output
        if (len(embed.fields) % 3) == 1:
            embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
        explosive_emoji = check_emoji(guild.emojis, ''.join(explosive.split('.')))
        embed_name = str(explosive_emoji) + ' x' + str(sulfur // explosive_dict[explosive])
        embed_value = str(sulfur % explosive_dict[explosive]) + str(sulfur_emoji) + ' left over'
        embed.add_field(name=embed_name, value=embed_value, inline=True)
    return embed


# Cross references skins of a certain type with a master list of skins and their current prices retrieved from
# Bitskins API. This is used to get all skins of skin_type and their current prices, which will then be sorted
# to display aggregate data on said skins
def cross_reference_skins(skin_type=''):
    if skin_type == '':
        sql = "SELECT skin_name, link, initial_price, release_date, skin_img FROM skin"
        cursor.execute(sql)
        data = cursor.fetchall()
        skin_price_list = get_skin_prices()
        cross_referenced_skin_list = []
        for skin in data:
            # Attempt to add a skin to the list. If there is a key error, then the skin was added this week and has
            # no market data. Thus, we can skip it.
            try:
                cross_referenced_skin_list.append(
                    PriceSkin(skin[0], skin[1], skin[2], skin[3], skin_price_list[skin[0]], skin[4]))
            except KeyError:
                pass
        return cross_referenced_skin_list
    else:
        # Get all skins of skin_type from the database
        skin_list, best_skin = get_skins_of_type(skin_type)
        # Get all skins and their prices from Bitskins API
        skin_price_list = get_skin_prices()
        # List of PriceSkin Objects. Each object is a skin for item skin_type
        cross_referenced_skin_list = []
        for skin in skin_list:
            # Attempt to add a skin to the list. If there is a key error, then the skin was added this week and has
            # no market data. Thus, we can skip it.
            try:
                cross_referenced_skin_list.append(
                    PriceSkin(skin[0], skin[1], skin[2], skin[3], skin_price_list[skin[0]], skin[4]))
            except KeyError as e:
                pass
        return cross_referenced_skin_list, best_skin


# Generates a list of PIL images for a list of skins from the item store
# @Param items: List of items from the rust item store
# @Param largest_string: Largest string found in the database. Used for padding
# @Return: List of PIL images corresponding each item in items
def gen_images(items, largest_string):
    img_list = []
    for item in items:
        # Get the item's data
        item_name = item.get_name()
        item_price = item.get_price()
        predicted_price = item.get_predicted_price()
        img_src = item.get_img_url()
        img_resp = requests.get(img_src)
        skin_img = Image.open(BytesIO(img_resp.content))

        # Set icon size and font type/size
        icon_size = 64, 64
        fnt = ImageFont.truetype("whitneysemibold.ttf", 20)
        # Set the image height and width. The height is the height of the icon and width is
        # set to the longest string size
        img_height = icon_size[0]
        # Total width of the image is 64 + space b/tween img and text + longest string possible
        img_width = icon_size[1] + (fnt.getsize('\t' + largest_string + '\t\t$99.99\t\t$99.99')[0])
        img = Image.new(mode="RGBA", size=(img_width, img_height), color=(0, 0, 0, 0))

        # Draw skin's image on a transparent image and write the item's data as text
        skin_img.thumbnail(icon_size, Image.ANTIALIAS)
        img.paste(skin_img, (0, 0), skin_img)
        d = ImageDraw.Draw(img)
        paste_str = '\t' + item_name + '\t\t' + str(item_price) + ' -> $' + str(predicted_price)

        # Right justify the text so it looks nicer
        text_length = fnt.getsize(paste_str)[0]
        paste_x = img_width - text_length

        d.text((paste_x, ((icon_size[1] // 2) - 20)), paste_str, font=fnt,
               fill=(255, 255, 255))
        img_list.append(img)
    return img_list


# Formats a list of strings into multiple columns of equal width
# @Param str_list: List of strings to columnize
# @Param cols: Number of columns
# @Return: Formatted string representing all items in str_list
def format_text(str_list, cols):
    # Get the length of the longest string in the list
    try:
        max_width = max(map(lambda x: len(x), str_list))
    except ValueError as e:
        return ''
    # Justify all strings to the left
    justify_list = list(map(lambda x: x.ljust(max_width), str_list))
    # Pad the columns to equal widths
    lines = (' '.join(justify_list[i:i + cols]) for i in range(0, len(justify_list), cols))
    # Join all lines and return the resulting string
    return lines


# Generates all emojis needed for cambot
def gen_emojis():
    # Create a dictionary to store the emojis
    emoji_dict = {}
    # Images needed for the emojis are stored in the 'img' folder
    for f in os.listdir('img'):
        img_path = os.path.join('img', f)
        # Add the name of each image and the image itself as a bytes stream to the dictionary
        # Remove the file extension from the name and re-join the items after splitting. We re-join the items
        # in case there is a . in hte image name
        image_name = ''.join(f.split('.')[:-1])
        with open(img_path, 'rb') as image:
            img_read = image.read()
            b = bytearray(img_read)
            emoji_dict[image_name] = b

    return emoji_dict


# Checks if an item can be represented by an emoji
# @Param guild_emojis: All emojis in the current server
# @Param item_str: Item we are checking
# @Return emoji: Corresponding emoji if found, None if not
def check_emoji(guild_emojis, item_str):
    for emoji in guild_emojis:
        # Strip all _ characters and remove the cambot prefix from all emotes in the server
        emoji_name = emoji.name.split('_')[1:]
        emoji_name = ' '.join(emoji_name)
        if emoji_name == item_str.lower():
            return emoji
    return item_str.title()


# Checks if our emojis are already in the guild
# @Param guild_emojis: All emojis in the current guild
# @Return missing_emojis: All of CamBots emojis not in the server.
def check_guild_emojis(guild_emojis):
    # Get all emote names from the image files in the 'img' folder
    missing_emoji_names = []
    for f in os.listdir('img'):
        img_name = ''.join(f.split('.')[:-1]).replace('_', ' ')
        missing_emoji_names.append(img_name.lower())

    print(missing_emoji_names)
    # Create a copy of the missing_emojis array to remove items from
    missing_emojis = missing_emoji_names.copy()

    # Go through all of cambot's emotes and check if they are already in the server
    for cam_emoji_name in missing_emoji_names:
        for guild_emoji in guild_emojis:
            guild_emoji_name = guild_emoji.name.split('_')[1:]
            guild_emoji_name = ' '.join(guild_emoji_name)
            # If the emotes are already in the server's emote list, remove them from the missing emoji list
            if guild_emoji_name == cam_emoji_name:
                missing_emojis.remove(cam_emoji_name)

    return missing_emojis


def get_uptime(start_time):
    curr_time = datetime.now()
    elapsed_time = curr_time - start_time
    seconds = elapsed_time.seconds
    hours = seconds // 3600
    if hours > 1:
        seconds -= hours * 3600
    minutes = seconds // 60
    if minutes > 1:
        seconds -= minutes * 60
    output = str(elapsed_time.days) + 'd, ' + str(hours) + 'h, ' + str(minutes) + 'm, ' + str(seconds) + 's'
    return output


# Adds all missing emojis to the corresponding guild
# @Param guild: Guild we are adding emojis to
# @Return: String status of emoji addition
async def add_emojis(guild):
    # Get all missing emojis in the current guild
    guild_emojis = guild.emojis
    missing_emojis = check_guild_emojis(guild_emojis)

    # Get the number of free emoji slots for the guild
    available_emojis = guild.emoji_limit - len(guild_emojis)

    # If there are no missing emojis, let the user know they have all of cambots emojis
    if not missing_emojis:
        return 'All emojis are already in the server'
    else:
        # If there is space for the emojis, generate them
        if available_emojis > len(missing_emojis):
            emojis = gen_emojis()
            emoji_names = emojis.keys()
            # Generate all emotes in the missing_emojis list
            for name in emoji_names:
                temp_name = name.replace('_', ' ')
                if temp_name in missing_emojis:
                    final_name = 'cambot_' + name
                    print('Creating emoji with name ' + final_name)
                    await guild.create_custom_emoji(name=final_name, image=emojis[name])

            return 'Successfully created all emojis'
        # If there isn't enough space, tell the user to remove x amount of emotes
        else:
            return 'You do not have enough emoji slots to add the emotes. Remove ' + str(len(missing_emojis)) \
                   + ' emote(s) and try again'


# Removes all of cambot's emojis from the current guild
# @Param guild: Guild to remove emojis from
# @Return: String representing the status of the removal
async def remove_emojis(guild):
    emojis = guild.emojis

    # Get emoji names for all emojis added by the bot
    img_names = []
    for f in os.listdir('img'):
        img_names.append(f.split('.')[0])

    for emoji in emojis:
        # Remove the first word before an underscore and check if the resulting name is in the name of images
        temp_name = emoji.name.split('_')[1:]
        temp_name = '_'.join(temp_name)
        # If the emoji is one generated by the bot, remove it.
        if temp_name in img_names:
            print('Deleting emoji ' + temp_name)
            await emoji.delete()
    return 'All emojis from CamBot have been removed successfully'


# Generates the initial embed for the skinlist command and inserts all other pages into the
# skinlist_messages database
# @Param sorted_by_prices: List of 10 skins sorted by a certain price
# @Param channel: Channel to output the embed
async def display_skinlist_embed(sorted_by_price, channel, title_string, embed_name):
    # Get the link for each item and output it in an embed
    i = 0
    for s in sorted_by_price:
        try:
            name = s
            sql = "SELECT link, skin_img FROM skin WHERE skin_name = ?"
            cursor.execute(sql, (name,))
            data = cursor.fetchall()[0]
            link = data[0]
            thumbnail = data[1]
            price = '$' + str(sorted_by_price[name])
        except sqlite3.InterfaceError:
            link = s.l
            thumbnail = s.img
            name = s.n
            if embed_name == 'Price':
                price = '$' + str(s.cp)
            elif embed_name == 'Percent change':
                price = str(s.pc) + '%'
        if i == 0:
            # Display the first item we get in an embed. This is done using a counter because we need
            # The link for the item which is generated in this loop but only the first item needs
            # to be displayed and we would lose the item link upon looping. I could query for the first
            # item with the channel and message ids but I think this is faster
            embed = discord.Embed(title=name, url=link)
            embed.set_thumbnail(url=thumbnail)
            footer_text = 'Page 1/' + str(len(sorted_by_price))
            embed.set_footer(text=footer_text)
            embed.add_field(name=embed_name, value=price, inline=True)
            msg = await channel.send(title_string, embed=embed)
            # React to the message to set up navigation
            await msg.add_reaction('◀')
            await msg.add_reaction('▶')
        # Insert all other items into the SQL database with corresponding message and channel ids
        try:
            sql = "INSERT INTO skinlist_messages (message_id, channel_id, item_name, item_data, " \
                  "store_url, img_link) VALUES(?, ?, ?, ?, ?, ?)"
            val = (msg.id, channel.id, name, price, link, thumbnail)
            cursor.execute(sql, val)
            connection.commit()
        except Exception as e:
            print(e)
        i += 1


# Generates an embed for Rust skins
# @Param position: Current location of the message we want to display
# @Param table_name: Name of the table where the message was found
# @Param pages: All items returned from an SQL query getting items associated with a message
def gen_embed(curr_position, table_name, pages, guild):
    if table_name == 'durability_messages':
        best_building = pages[0][2]
        side = pages[0][3]
        embed_title = 'Displaying the durability of ' + side + ' side ' + best_building
        item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
        cursor.execute(item_sql, (best_building,))
        item_data = cursor.fetchall()[0]
        building_url = item_data[1]
        item_img = item_data[0]

        # Get durability data that applies to both sides
        durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = "both" ORDER BY 
                                        tool_sulfur_cost DESC'''
        cursor.execute(durability_sql, (best_building,))
        building_data = cursor.fetchall()

        # Get all data from the durability table in the database corresponding to the desired side
        durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = ? ORDER BY 
                                        tool_sulfur_cost DESC'''
        cursor.execute(durability_sql, (best_building, side))
        building_data.extend(cursor.fetchall())

        # Create the embed and set the title, URL, image, and footer
        embed = discord.Embed(title=embed_title, url=building_url)
        embed.set_thumbnail(url=item_img)
        max_pages = math.ceil(len(building_data) / 24)
        if curr_position == 0:
            curr_position = max_pages
            footer_text = 'Page ' + str(max_pages) + '/' + str(max_pages)
        else:
            footer_text = 'Page ' + str(curr_position) + '/' + str(max_pages)
        embed.set_footer(text=footer_text)

        # Loop through the data and add it to the embed
        for row in building_data:

            if len(embed.fields) >= 24:
                # Once we fill the next page, return it
                return embed
            # If the current row is not in the index range of the page we are on, skip it
            elif row in building_data[(curr_position - 1) * 24:((curr_position - 1) * 24) + 24]:
                embed_value = 'Quantity: ' + row[3] + '\nTime: ' + row[4]
                if row[5]:
                    embed_value += '\nSulfur cost: ' + row[5]
                embed.add_field(name=row[2], value=embed_value, inline=True)
        return embed
    elif table_name == 'harvest_messages':
        best_tool = pages[0][2]
        embed_title = 'Displaying the harvesting data for the ' + best_tool
        item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
        cursor.execute(item_sql, (best_tool,))
        item_data = cursor.fetchall()[0]
        building_url = item_data[1]
        item_img = item_data[0]

        # Get durability data that applies to both sides
        sql = '''SELECT DISTINCT node_name FROM harvesting WHERE item_name = ? ORDER BY resource_name ASC'''
        cursor.execute(sql, (best_tool,))
        harvest_nodes = cursor.fetchall()

        # Create the embed and set the title, URL, image, and footer
        embed = discord.Embed(title=embed_title, url=building_url)
        embed.set_thumbnail(url=item_img)
        max_pages = math.ceil(len(harvest_nodes) / 24)
        if curr_position == 0:
            curr_position = max_pages
            footer_text = 'Page ' + str(max_pages) + '/' + str(max_pages)
        else:
            footer_text = 'Page ' + str(curr_position) + '/' + str(max_pages)
        embed.set_footer(text=footer_text)

        # Loop through the data and add it to the embed
        for node in harvest_nodes:
            if len(embed.fields) >= 24:
                return embed
            elif node in harvest_nodes[(curr_position - 1) * 24:((curr_position - 1) * 24) + 24]:
                sql = '''SELECT resource_name, resource_quantity, time FROM harvesting WHERE item_name = ?
                                           AND node_name = ?'''
                cursor.execute(sql, (best_tool, node[0]))
                resources = cursor.fetchall()
                embed_value = ''
                for resource in resources:
                    embed_value += resource[1] + ' ' + str(check_emoji(guild.emojis, resource[0])) + '\n'
                embed_value += 'Time: ' + resource[2]
                embed.add_field(name=node[0], value=embed_value, inline=True)
        return embed

        # Loop through the data and add it to the embed
        for row in building_data:

            if len(embed.fields) >= 24:
                # Once we fill the next page, return it
                return embed
            # If the current row is not in the index range of the page we are on, skip it
            elif row in building_data[(curr_position - 1) * 24:((curr_position - 1) * 24) + 24]:
                embed_value = 'Quantity: ' + row[3] + '\nTime: ' + row[4]
                if row[5]:
                    embed_value += '\nSulfur cost: ' + row[5]
                embed.add_field(name=row[2], value=embed_value, inline=True)
        return embed
    elif table_name == 'item_store_messages':
        # The message origin was for the new rust skins, format all data accordingly
        # Generate embed with title and data corresponding to the given skin from SQLite file
        embed = discord.Embed(title=pages[curr_position - 1][2],
                              url='https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        embed.set_thumbnail(url=pages[curr_position - 1][5])
        if curr_position == 0:
            footer_text = 'Page ' + str(len(pages)) + '/' + str(len(pages))
        else:
            footer_text = 'Page ' + str(curr_position) + '/' + str(len(pages))
        embed.set_footer(text=footer_text)
        embed.add_field(name='Item price', value=pages[curr_position - 1][3], inline=True)
        embed.add_field(name='Predicted price(1yr)', value=pages[curr_position - 1][4], inline=True)
        return embed
    elif table_name == 'skinlist_messages':
        # The message origin was for a skinlist command. Format all data accordingly
        # Generate embed with title and data corresponding to the given skin from the SQLite file
        embed = discord.Embed(title=pages[curr_position - 1][2],
                              url=pages[curr_position - 1][4])
        embed.set_thumbnail(url=pages[curr_position - 1][5])
        if curr_position == 0:
            footer_text = 'Page ' + str(len(pages)) + '/' + str(len(pages))
        else:
            footer_text = 'Page ' + str(curr_position) + '/' + str(len(pages))
        embed.set_footer(text=footer_text)
        # Determine if the message displayed is using percent difference or price data by checking if a
        # percent sign is in the value field
        if '%' in pages[curr_position - 1][3]:
            embed.add_field(name='Percent change', value=pages[curr_position - 1][3], inline=True)
        else:
            embed.add_field(name='Price', value=pages[curr_position - 1][3], inline=True)
        return embed


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))
    global CAMBOT_START_TIME
    CAMBOT_START_TIME = datetime.now()


@client.event
# This function runs whenever someone joins or leaves a voice channel. I mainly made it for my personal discord server,
# but it will work with any other server as long as they have a 'rust' voice channel and 'squaddies' text channel
async def on_voice_state_update(member, before, after):
    # If the user left the server check if they left the rust channel
    if after.channel is None:
        if before.channel.name.lower() == 'rust':
            output_channel = ''
            # Get the output server, in this case it will be squaddies
            for channel in member.guild.channels:
                if channel.name.lower() == 'squaddies':
                    output_channel = channel
            if output_channel == '':
                pass
            # Print a leaving message
            else:
                leave_string = ''
                with open('C:/Users/Stefon/PycharmProjects/CamBot/leavestrings.txt') as leave:
                    leave_strings = leave.read().splitlines()
                    leave_string = random.choice(leave_strings)
                    f.close()
                # If an exception is raised when trying to send a message, then the channel is a voice channel
                try:
                    await output_channel.send(member.name + ' left ' + leave_string)
                except Exception as e:
                    print('SQUADDIES IS NOT A TEXT CHANNEL NOT HOTTTT')

    # If the user didn't leave the server, check if they moved to the 'rust' channel
    elif after.channel.name.lower() == 'rust':
        # If a user mute/unmutes this event will trigger. Check if the channels are the same and do nothing if they are
        # Check if we are joining a channel from outside the server
        if before.channel is not None:
            if before.channel == after.channel:
                return
        output_channel = ''
        # Get the output server, in this case it will be named squaddies
        for channel in member.guild.channels:
            if channel.name.lower() == 'squaddies':
                output_channel = channel
        # Print a join message
        if output_channel == '':
            pass
        else:
            join_string = ''
            with open('C:/Users/Stefon/PycharmProjects/CamBot/joinstrings.txt') as join:
                join_strings = join.read().splitlines()
                join_string = random.choice(join_strings)
                f.close()
            # If an exception is raised when trying to send a message, then squaddies is not a text channel
            try:
                await output_channel.send(member.name + ' joined ' + join_string)
            except Exception as e:
                print('SQUADDIES IS NOT A TEXT CHANNEL NOT HOTTTT')


@client.event
async def on_raw_reaction_add(reaction):
    # Omit the bot's reactions
    if reaction.user_id == client.user.id:
        pass
    else:
        # Get the channel and message id of the reaction
        channel = await client.fetch_channel(reaction.channel_id)
        msg = await channel.fetch_message(reaction.message_id)
        if msg:
            # Query all tables that use dynamic embeds for the message
            tables = ['durability_messages', 'item_store_messages', 'skinlist_messages', 'harvest_messages']
            pages = []
            # Check for the message in each table until we find it
            for table in tables:
                sql = "SELECT * FROM " + table + " WHERE message_id = ? AND channel_id = ?"
                val = (msg.id, channel.id)
                cursor.execute(sql, val)
                pages = cursor.fetchall()
                # If we find the message, generate an embed for the next position
                if pages:
                    # Get the current position from the footer text
                    footer_text = msg.embeds[0].footer.text
                    position = int(footer_text[footer_text.find('Page ') + len('Page '):footer_text.rfind('/')])
                    max_pages = int(footer_text.split('/')[1])
                    # Check if the emoji is a valid scrolling emote and set the direction accordingly
                    if str(reaction.emoji) == '◀':
                        await msg.remove_reaction('◀', reaction.member)
                        position -= 1
                    elif str(reaction.emoji) == '▶':
                        await msg.remove_reaction('▶', reaction.member)
                        if position >= max_pages:
                            position = 1
                        else:
                            position += 1
                    else:
                        # If the emoji isn't valid, return
                        return
                    # Generate a new embed, set the message to it, and return
                    embed = gen_embed(position, table, pages, msg.channel.guild)
                    await msg.edit(embed=embed)
                    break


@client.event
async def on_guild_join(guild):
    # Initialize emojis whenever the bot is added to the guild
    await guild.text_channels[0].send('OOOO CAMBOT COMING IN HOT SPICY DICEY. ADDING EMOJIS')
    result = await add_emojis(guild)
    await guild.text_channels[0].send(result)


@client.event
async def on_message(message):
    message_text = message.content.lower()
    command_start = timer()
    # Ignore messages from the bot to avoid infinite looping and ignore messages that aren't commands
    if message.author == client.user or not message_text.startswith('!'):
        return
    # Display all commands / get cambot's uptime and server stats
    if message_text.startswith('!cambot'):
        args = message_text.split()
        if len(args) > 1 and args[1] == 'info':
            uptime = get_uptime(CAMBOT_START_TIME)
            num_servers = len(client.guilds)
            embed = discord.Embed(title="Cambot provides useful data for skins/items in Rust",
                                  description="[Add Cambot to your server](https://discord.com/oauth2/authorize?c"
                                              "lient_id=684058359686889483&permissions=8&scope=bot)")

            embed.add_field(name="Uptime", value=uptime, inline=True)
            embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
            embed.add_field(name="Connected servers", value=num_servers, inline=True)
            avatar = client.user.avatar_url
            embed.set_thumbnail(url=avatar)
            await message.channel.send(embed=embed)

        else:
            embed = discord.Embed()
            embed.add_field(name="**!craftcalc**", value="Outputs the recipe of an item", inline=True)
            embed.add_field(name="**!status**", value="Outputs the current status of CamBot's dependent servers",
                            inline=True)
            embed.add_field(name="**!serverpop**", value="Outputs the current pop of any server", inline=True)
            embed.add_field(name="**!devblog**", value="Posts a link to the newest devblog with a short summary",
                            inline=True)
            embed.add_field(name="**!rustnews**", value="Posts a link to the latest news on Rust's development info",
                            inline=True)
            embed.add_field(name="**!rustitems**", value="Displays all items on the Rust store along with prices",
                            inline=True)
            embed.add_field(name="**!droptable**", value="Outputs the drop table for a crate/NPC", inline=True)
            embed.add_field(name="**!lootfrom**", value="Outputs drop rates for a specific item", inline=True)
            embed.add_field(name="**!sulfur**",
                            value="Outputs how many explosives you can craft with a specific sulfur "
                                  "amount", inline=True)
            embed.add_field(name="**!furnaceratios**",
                            value="Shows the most efficient furnace ratios for a given furnace "
                                  "and ore type", inline=True)
            embed.add_field(name="**!campic**", value="Posts a HOT pic of Cammy", inline=True),
            embed.add_field(name="**!recycle**", value="Displays the output of recycling an item", inline=True),
            embed.add_field(name="**!skindata**", value="Displays skin price data for an item", inline=True)
            embed.add_field(name="**!stats**", value="Outputs the stats of a given item(weapon, armor, etc)",
                            inline=True)
            embed.add_field(name="**!repair**", value="Outputs the cost to repair an item", inline=True)
            embed.add_field(name="**!binds**", value="Displays all supported commands to bind", inline=True)
            embed.add_field(name="**!gamble**", value="Displays bandit camp wheel percentages and calculates the "
                                                      "chance of a certain outcome occuring", inline=True)
            embed.add_field(name="**!skinlist**", value="Displays a list of skins for a certain item"
                                                        " for a certain item", inline=True)
            embed.add_field(name="**!raidcalc**", value="Calculates how many rockets/c4/etc to get through a certain"
                                                        " amount of walls/doors", inline=True)
            embed.add_field(name="**!durability**", value="Displays how much of various tools/explosives it takes"
                                                          " to get through a certain building item", inline=True)
            embed.add_field(name="**!experiment**",
                            value="Displays experiment tables of the tier 1, 2, and 3 workbenches",
                            inline=True)
            embed.add_field(name="**!cambot info**",
                            value="Displays uptime, connected servers, and a join link for Cambot",
                            inline=True)
            await message.channel.send('Here is a list of commands. For more info on a specific command, use '
                                       '**![commandName]**\n', embed=embed)

    elif message_text.startswith('!composting'):
        args = message_text.split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            # Rejoin all args after !droptable to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            sql = '''SELECT * FROM composting ORDER BY compost_amount DESC'''
            cursor.execute(sql)
            rows = cursor.fetchall()

            if not rows:
                await message.channel.send('No composting data. This should not happen')

            str_items = []
            for row in rows:
                str_items.append(row[0].ljust(28) + '\t' + str(row[1]).rjust(6))

            table_lines = format_text(str_items, 3)
            await message.channel.send('Displaying composting table for all items. Use **!composting [itemName] '
                                       'for data about a specific item :\n')
            # For each line we are trying to output, check if adding it would put us close to the message length
            # limit. If we are approaching it, post the current string and start a new one
            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await message.channel.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await message.channel.send('```' + output_msg + '```')
        # If the user enters a table name, search for it
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, container_name)

            sql = '''SELECT * FROM composting WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            title_str = 'Displaying composting data of ' + best_item
            embed = discord.Embed(title=title_str, url=item_url)
            embed.add_field(name='Compost amount', value=rows[0][1], inline=True)
            amount_per_compost = math.ceil(1 / float(rows[0][1]))
            embed.add_field(name='Amount for 1 compost', value=amount_per_compost, inline=True)
            embed.set_thumbnail(url=item_img)
            await message.channel.send(embed=embed)

    elif message_text.startswith('!steamstats'):
        args = message_text.split()
        if len(args) == 1:
            title = '!steamstats displays the total concurrent players of the input game at the current time'
            description = 'Use **!steamstats [gameName]**'
            embed = discord.Embed(title=title, description=description)
            await message.channel.send(embed=embed)
        else:
            game_name = ' '.join(args[1:])
            game_name = game_name.replace(' ', '+')
            game_name = game_name.replace('&', '%26')
            game_name = game_name.replace('?', '%3F')
            url = 'https://steamcharts.com/search/?q=' + game_name

            search_html = get_html(url)
            table = search_html.find('tbody')
            if not table:
                title = game_name + ' has no player data'
                await message.channel.send(title)

            rows = table.find_all('tr')
            results = {}

            for row in rows:
                game_stats = []
                cols = row.find_all('td')
                result_name = cols[1].find('a').text
                players = cols[2].text
                month_avg = cols[3].text
                month_gain = cols[4].text
                # Skip duplicates as they have less players
                if result_name not in results:
                    results[result_name] = game_stats
                    game_stats.append(players)
                    game_stats.append(month_avg)
                    game_stats.append(month_gain)

            best_game = get_string_best_match(results.keys(), game_name)

            data = results[best_game]
            fields = {'Current Players': data[0], 'Month Average': data[1], 'Monthly Gain/Loss': data[2]}
            title = 'Displaying steam player data for ' + best_game
            embed = format_embed(fields, title, None, None, None, None)
            await message.channel.send(embed=embed)

    elif message_text.startswith('!harvesting'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            title = '!harvesting displays how many materials you get for harvesting things with a certain tool'
            description = 'Use **!harvesting [toolName]**'
            embed = discord.Embed(title=title, description=description)
            await message.channel.send(embed=embed)
        # If the user entered arguments, get the arguments to determine what to do
        else:
            tool_name = ' '.join(args[1:])

            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_tool = get_string_best_match(item_name_list, tool_name)
            # Get the item's link and image for the embed
            embed_title = 'Displaying harvesting data for the ' + best_tool
            item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(item_sql, (best_tool,))
            item_data = cursor.fetchall()[0]
            building_url = item_data[1]
            item_img = item_data[0]

            # Get durability data that applies to both sides
            sql = '''SELECT DISTINCT node_name FROM harvesting WHERE item_name = ? ORDER BY resource_name ASC'''
            cursor.execute(sql, (best_tool,))
            harvest_nodes = cursor.fetchall()

            if not harvest_nodes:
                await message.channel.send(best_tool + ' has no harvesting data')
                return

            # Create the embed and set the title and URL
            embed = discord.Embed(title=embed_title, url=building_url)
            embed.set_thumbnail(url=item_img)

            num_items = len(harvest_nodes)

            # Loop through the data and add it to the embed
            for node in harvest_nodes:
                if len(embed.fields) >= 24:
                    break
                sql = '''SELECT resource_name, resource_quantity, time FROM harvesting WHERE item_name = ?
                        AND node_name = ?'''
                cursor.execute(sql, (best_tool, node[0]))
                resources = cursor.fetchall()
                embed_value = ''
                for resource in resources:
                    embed_value += resource[1] + ' ' + str(check_emoji(message.channel.guild.emojis, resource[0])) + '\n'
                embed_value += 'Time: ' + resource[2]
                embed.add_field(name=node[0], value=embed_value, inline=True)
            if num_items > 24:
                num_pages = math.ceil(num_items / 24)
                footer_text = 'Page 1/' + str(num_pages)
                embed.set_footer(text=footer_text)
                msg = await message.channel.send(embed=embed)
                # React to the message to set up navigation if there is going to be more than 1 page
                await msg.add_reaction('◀')
                await msg.add_reaction('▶')
                # Insert message data into database file
                sql = '''INSERT INTO harvest_messages (message_id, channel_id, item_name) VALUES (?, ?, ?)'''
                cursor.execute(sql, (msg.id, message.channel.id, best_tool))
                connection.commit()

            else:
                # If there is only one page, don't bother setting up a dynamic embed
                await message.channel.send(embed=embed)

    elif message_text.startswith('!trades'):
        args = message_text.split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            embed = discord.Embed(title='This command displays all trades involving a specific item.',
                                  description = 'Use **!trades [itemName]**')
            await message.channel.send(embed=embed)
        # If the user enters an item name, search for it
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, container_name)

            sql = '''SELECT * FROM trades WHERE give_item = ? OR receive_item = ? ORDER BY shop_name'''
            cursor.execute(sql, (best_item, best_item))
            trades = cursor.fetchall()

            title_str = 'Displaying all trades involving ' + best_item
            fields = {}

            if not trades:
                await message.channel.send('You cannot get ' + best_item + ' from a trade')
                return

            trade_str = ''
            for trade in trades:
                shop = trade[4]
                try:
                    fields[shop] += '\t' + trade[1] + ' ' + trade[0] + ' for ' + trade[3] + ' ' + trade[2] + '\n'
                except KeyError:
                    fields[shop] = '\t' + trade[1] + ' ' + trade[0] + ' for ' + trade[3] + ' ' + trade[2] + '\n'

            await message.channel.send(title_str)

            table_lines = []
            for field in fields:
                table_lines.append(field + '\n' + fields[field])

            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await message.channel.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await message.channel.send('```' + output_msg + '```')

    elif message_text.startswith('!damage'):
        args = message_text.split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            await message.channel.send('!trades displays damage stats for a specific item with all available'
                                       ' ammunition. Use **!damage [itemName]**')
        # If the user enters an item name, search for it
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            item_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, item_name)

            sql = '''SELECT DISTINCT ammo_name FROM damage WHERE weapon_name = ?'''
            cursor.execute(sql, (best_item,))
            all_ammo = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            title_str = 'Displaying damage stats for the ' + best_item
            fields = {}

            if not all_ammo:
                await message.channel.send(best_item + ' has no damage stats')
                return

            for ammo in all_ammo:
                sql = '''SELECT stat_name, stat_value FROM damage WHERE ammo_name = ? AND weapon_name = ?'''
                cursor.execute(sql, (ammo[0], best_item))
                stats = cursor.fetchall()
                stat_str = ''
                for stat in stats:
                    stat_str += stat[0] + ' ' + stat[1] + '\n'
                fields[ammo[0]] = stat_str
            embed = format_embed(fields, title_str, item_url, None, item_img, None)
            await message.channel.send(embed=embed)

    elif message_text.startswith('!mix'):
        args = message_text.split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            await message.channel.send('This commmand displays mixing recipes. Use **!mix [itemName]**')
        # If the user enters a table name, search for it
        else:
            num_crafts = 1
            try:
                num_crafts = int(args[-1])
                if args[-1] <= 0:
                    await message.channel.send('Please enter a valid number')
                item_name = ' '.join(args[1:-1])
            except Exception:
                # Rejoin all args after the command name to pass it onto get_best_match
                item_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, item_name)

            sql = '''SELECT * FROM mixing WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()[0]

            if not rows:
                await message.channel.send(best_item + ' has no mixing data')

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            title_str = 'Displaying mixing data of ' + str(num_crafts) + ' ' + best_item
            fields = {}
            for i in range(4):
                ingredient_name = rows[(i * 2) + 1]
                ingredient_quantity = rows[(i * 2) + 2]
                if ingredient_name and ingredient_quantity:
                    key = 'Ingredient ' + str(i + 1)
                    ingredient_emoji = check_emoji(message.channel.guild.emojis, ingredient_name)
                    value = str(ingredient_emoji) + ' x' + str(num_crafts * int(ingredient_quantity))
                    fields[key] = value

            key = 'Mixing Time'
            value = str(int(rows[-1]) * num_crafts) + ' seconds'
            fields[key] = value
            embed = format_embed(fields, title_str, item_url, None, item_img, None)
            await message.channel.send(embed=embed)

    elif message_text.startswith('!durability'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            await message.channel.send('This command displays the durability of a certain item. It will display the '
                                       'number of various explosives/tools to break one. Use '
                                       '**!durability [itemName] [-h or -s if there is a hard/soft side]**')
        # If the user entered arguments, get the arguments to determine what to do
        else:
            side = 'hard'
            # Check if there is a -h or -s flag at the end
            if args[-1] == '-h':
                # If there is a hard flag, make the building name all args except first and last
                building_name = ' '.join(args[1:-1])
            elif args[-1] == '-s':
                # If there is a soft flag, set the query variable to soft
                building_name = ' '.join(args[1:-1])
                side = 'soft'
            else:
                # If there is no flag, make the building name all args except the first
                building_name = ' '.join(args[1:])

            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_building = get_string_best_match(item_name_list, building_name)
            # Get the item's link and image for the embed
            embed_title = 'Displaying the durability of a ' + side + ' side ' + best_building
            item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(item_sql, (best_building,))
            item_data = cursor.fetchall()[0]
            building_url = item_data[1]
            item_img = item_data[0]

            # Get durability data that applies to both sides
            durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = "both" ORDER BY 
                                tool_sulfur_cost DESC'''
            cursor.execute(durability_sql, (best_building,))
            building_data = cursor.fetchall()

            # Get all data from the durability table in the database corresponding to the desired side
            durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = ? ORDER BY 
                                tool_sulfur_cost DESC'''
            cursor.execute(durability_sql, (best_building, side))
            building_data.extend(cursor.fetchall())
            # We want a max of 24 fields in an embed, so if there are more than that split the embed and make it
            # dynamic
            num_items = len(building_data)

            # Create the embed and set the title and URL
            embed = discord.Embed(title=embed_title, url=building_url)
            embed.set_thumbnail(url=item_img)

            # Loop through the data and add it to the embed
            for row in building_data:
                if len(embed.fields) >= 24:
                    break
                embed_value = 'Quantity: ' + row[3] + '\nTime: ' + row[4]
                if row[5]:
                    embed_value += '\nSulfur cost: ' + row[5]
                embed.add_field(name=row[2], value=embed_value, inline=True)
            if num_items > 24:
                num_pages = math.ceil(num_items / 24)
                footer_text = 'Page 1/' + str(num_pages)
                embed.set_footer(text=footer_text)
                msg = await message.channel.send(embed=embed)
                # React to the message to set up navigation if there is going to be more than 1 page
                await msg.add_reaction('◀')
                await msg.add_reaction('▶')
                # Insert message data into database file
                sql = '''INSERT INTO durability_messages (message_id, channel_id, building, side) VALUES (?, ?, ?, ?)'''
                cursor.execute(sql, (msg.id, message.channel.id, best_building, side))
                connection.commit()

            else:
                # If there is only one page, don't bother setting up a dynamic embed
                await message.channel.send(embed=embed)

    elif message_text.startswith('!experiment'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            await message.channel.send('This command displays the experiment tables for each workbench. Use '
                                       '**!experiment [1, 2, or 3]** to get tables for each respective workbench')
        # If the user entered arguments, get the arguments to determine what to do
        else:
            # Make sure the user entered a workbench tier
            try:
                tier = int(args[-1])
            except ValueError as e:
                await message.channel.send('Please enter a valid number')
                return
            # Ensure the tier was either 1, 2, or 3
            if tier == 1 or tier == 2 or tier == 3:
                sql = '''SELECT item_name FROM items WHERE workbench_tier = ?'''
                cursor.execute(sql, (str(tier),))
                # Convert tuples to list
                str_items = list(i[0] for i in cursor.fetchall())
                num_items = len(str_items)
                # Format table items into 5 columns and return each line in a generator
                table_lines = format_text(str_items, 3)

                await message.channel.send('Displaying the experiment table for **workbench level ' + str(tier)
                                           + '**:\n')
                # For each line we are trying to output, check if adding it would put us close to the message length
                # limit. If we are approaching it, post the current string and start a new one
                output_msg = ''
                for line in table_lines:
                    if len(output_msg) + len(line) > 1900:
                        await message.channel.send('```' + output_msg + '```')
                        output_msg = ''
                    output_msg += line + '\n'
                await message.channel.send('```' + output_msg + '```')
                await message.channel.send('The chance of getting one item is 1 in ' + str(num_items) + ' or '
                                           + '{0:.2f}'.format((1 / num_items) * 100) + '%')
            else:
                await message.channel.send('Please enter a valid number')
                return

    elif message_text.startswith('!raidcalc'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            await message.channel.send('This command displays the amount of rockets/c4/etc to get through a certain'
                                       ' amount of walls/doors. Use **!raidcalc [wall/door type] '
                                       '[number of walls/doors]**\n For multiple walls/doors, use a comma separated '
                                       'list. Ex: !raidcalc sheet wall 2, garage door 5')
        # If the user entered arguments, get the arguments to determine what to do
        else:
            # Rejoin the arguments without the command input
            args = ' '.join(args[1:])
            # Split the joined string by comma to separate buildings entered by the user
            buildings = args.split(',')

            total_min_sulfur = 0
            min_sulfur_string = ''
            embed = discord.Embed()
            # For each building block the user entered, get the sulfur cost of raiding it
            for building in buildings:
                # Get the amount of the current building the user wants to blow through
                building_args = building.split()
                # If we encounter a type error when attempting to cast the last argument in our current building, then
                # we assume the user only wants to destroy 1
                num_building = 0
                building_name = []
                try:
                    num_building = int(building_args[-1])
                    for building_arg in building_args:
                        # In the case that we are able to cast the last argument to an int, append all arguments but the
                        # last(which is the number) to the item's name
                        if not building_arg == building_args[-1]:
                            building_name.append(building_arg)
                except ValueError as e:
                    num_building = 1
                    # In the case that we are unable to cast the name to an int, then add all arguments to the item
                    # name
                    for building_arg in building_args:
                        building_name.append(building_arg)
                if num_building <= 0:
                    await message.channel.send('Please enter a positive integer')
                    return
                building_name = ' '.join(building_name)
                # Once we have the building name, search for the best matching one based on the user's search term
                with open('item_names.txt') as file:
                    item_name_list = file.read().splitlines()
                    file.close()
                best_building = get_string_best_match(item_name_list, building_name)
                # Get explosive data for the specified building
                sql = '''SELECT tool_name, tool_quantity, tool_sulfur_cost FROM durability WHERE item_name = ? 
                AND  (item_side = "hard" OR item_side = "both") 
                AND (tool_name = "Timed Explosive Charge" OR tool_name = "Rocket" OR tool_name = 
                "Explosive 5.56 Rifle Ammo" OR tool_name = "Satchel Charge");'''
                cursor.execute(sql, (best_building,))
                all_explosives = cursor.fetchall()

                embed_name = 'To get through ' + str(num_building) + ' ' + best_building + ', you would need:'
                # These two variables will be used to calculate the minimum sulfur for the current building item
                min_sulfur = 999999
                lowest_explosive = ''
                # Check if the server has the cambot sulfur emote. If not, display the string 'sulfur' instead of an
                # emote
                sulfur_emote = check_emoji(message.channel.guild.emojis, 'sulfur')
                # Iterate through the list of all explosives and only get the data of the ones we are looking for
                explosive_cost = ''
                for explosive in all_explosives:
                    explosive_name = explosive[0]
                    explosive_quantity = explosive[1]
                    curr_sulfur = int(explosive[2])
                    # Get the item name, quantity, and sulfur cost. Check for the emoji corresponding to the
                    # current explosive
                    explosive_emoji = check_emoji(message.channel.guild.emojis,
                                                  ''.join(explosive_name.split('.')))
                    curr_cost = '\n' + str(explosive_emoji) + '\tx' + \
                                str(num_building * int(explosive_quantity)) + ' (' + str(curr_sulfur) + \
                                str(sulfur_emote) + ')'

                    explosive_cost += curr_cost
                    if curr_sulfur < min_sulfur:
                        min_sulfur = curr_sulfur
                        lowest_explosive = curr_cost + ' for the ' + building_name
                        if num_building > 1:
                            lowest_explosive += 's'
                embed.add_field(name=embed_name, value=explosive_cost, inline=False)
                # If the minimum didn't change, then the item cannot be broken
                if min_sulfur == 999999:
                    await message.channel.send('You cannot break one or more of the items you entered')
                    return
                else:
                    # Add minimum sulfur cost to the total minimum
                    total_min_sulfur += min_sulfur
                    min_sulfur_string += lowest_explosive
            min_name = 'The cheapest path would cost ' + str(total_min_sulfur) + str(sulfur_emote) + ' by using:'
            embed.add_field(name=min_name, value=min_sulfur_string, inline=False)
            await message.channel.send(embed=embed)


    elif message_text.startswith('!skinlist'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            await message.channel.send('This command displays aggregate skin data. Use **!skinlist -c, -e, -lp, or '
                                       '-mp [itemType]** for the top 10 cheapest, most expensive, least profitable, or'
                                       ' most profitable skins for that item. Additionally, you can use these without '
                                       'any item type for the top 10 cheapest/etc skins for all items\n '
                                       'Use **!skinlist [itemType]** to display *all* skins of that item type'
                                       '(this list may be long!)')
        # If the user entered arguments, get the arguments to determine what to do
        elif args[1] == '-c':
            search_type = ' '.join(args[2:])
            # If there are no arguments after -c, then display the cheapest skins of all categories
            if search_type == '':
                # Get all items names and their prices from Bitskins API
                skin_price_list = get_skin_prices()
                # Sort the returned dictionary by price and take the 10 lowest values
                sorted_by_price = {k: v for k, v in sorted(skin_price_list.items(), key=lambda ite: float(ite[1]))[:10]}
                # Once we have a sorted dictionary, display the data and add it to the database
                await display_skinlist_embed(sorted_by_price, message.channel,
                                             'Displaying the 10 cheapest skins on the market:', 'Price')

            else:
                # Get a list of objects containing all items of search_type
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.cp))[:10]
                msg_text = 'Displaying the 10 cheapest skins for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, message.channel, msg_text, 'Price')
        elif args[1] == '-e':
            search_type = ' '.join(args[2:])
            # If there are no arguments after -e, then display the cheapest skins of all categories
            if search_type == '':
                # Get item names and prices of all items using Bitskins API
                skin_price_list = get_skin_prices()
                # Sort the list by price and take the 10 highest values
                sorted_by_price = {k: v for k, v in sorted(skin_price_list.items(), key=lambda ite: float(ite[1]),
                                                           reverse=True)[:10]}
                await display_skinlist_embed(sorted_by_price, message.channel,
                                             'Displaying the 10 most expensive skins on the market:', 'Price')

            else:
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 most expensive skins for
                # skin_type in this case. This is pretty much the same as -c, except we reverse the sorting
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.cp), reverse=True)[:10]
                msg_text = 'Displaying the 10 most expensive skins for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, message.channel, msg_text, 'Price')

        elif args[1] == '-lp':
            search_type = ' '.join(args[2:])
            # If there are no arguments after -lp, then display the least profitable of all categories
            if search_type == '':
                # Get a list of objects containing all items in rust. I cannot simply use the Bitskins API for this
                # like with -c and -e since I need current price which can only be found in my database. Thus,
                # I have to combine my database and Bitskins to get the %profit
                skin_list = cross_reference_skins()
                # Once we have the skins, sort them by percent profit and take the 10 lowest values
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc))[:10]
                await display_skinlist_embed(sorted_by_price, message.channel,
                                             'Displaying the 10 skins with the worst profit:', 'Percent change')

            else:
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc))[:10]
                msg_text = 'Displaying the 10 skins with the worst profit for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, message.channel, msg_text, 'Percent change')

        elif args[1] == '-mp':
            search_type = ' '.join(args[2:])
            # If there are no arguments after -lp, then display the least profitable of all categories
            if search_type == '':
                # Get a list of objects containing all items in rust. I cannot simply use the Bitskins API for this
                # like with -c and -e since I need current price which can only be found in my database. Thus,
                # I have to combine my database and Bitskins to get the %profit
                skin_list = cross_reference_skins()
                # Once we have the list of skins, sort them by %profit and take the 10 highest values
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc), reverse=True)[:10]
                await display_skinlist_embed(sorted_by_price, message.channel,
                                             'Displaying the 10 skins with the best profit:', 'Percent change')

            else:
                skin_list, best_skin = cross_reference_skins(' '.join(args[2:]))
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc), reverse=True)[:10]
                msg_text = 'Displaying the 10 skins with highest returns for ' + best_skin + ':'
                await display_skinlist_embed(sorted_by_price, message.channel, msg_text, 'Percent change')

        else:
            skin_type = ' '.join(args[1:])
            data, best_skin = get_skins_of_type(skin_type)
            # Theoretically, there should always be a match but if there isn't exit the command and let the user know
            if not data:
                await message.channel.send('No skin data found for the given skin. Use **!skinlist [skinname]**\n')
                return
            else:
                desc = ''
                # Once we have the data, display it in an embed. Since there will be potentially hundreds of skins,
                # do not display one skin per line. Instead, separate them with |s.
                await message.channel.send('Displaying all skins for **' + best_skin + '**:')
                for d in data:
                    if len(desc) + len('[' + d[0] + '](' + d[1] + ') | ') >= 2000:
                        embed = discord.Embed(description=desc)
                        await message.channel.send(embed=embed)
                        desc = ""
                    else:
                        desc += '[' + d[0] + '](' + d[1] + ') | '
                embed = discord.Embed(description=desc)
                await message.channel.send(embed=embed)


    # Displays bandit camp wheel percentages and the chance of a certain outcome happening
    elif message_text.startswith('!gamble'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            outcome_text = "```1\t\t\t\t48%\n" \
                           "3\t\t\t\t24%\n" \
                           "5\t\t\t\t16%\n" \
                           "10\t\t\t\t8%\n" \
                           "20\t\t\t\t4%```"
            await message.channel.send('This command displays the percentages of hitting a certain number on the '
                                       'bandit '
                                       'camp wheel. Use **!gamble [num],[num],[num],etc** to get the chance for a '
                                       'series of outcomes to occur. Use a ! in front of a number for the probabilty '
                                       'of the wheel not landing on it\n' + outcome_text)
        # If the user entered arguments, get the odds of that string of outcomes occuring
        else:
            # Hardcoded percentages for the wheel
            percentages = {
                1: .48,
                3: .24,
                5: .16,
                10: .08,
                20: .04
            }
            # Get all arguments but the command into a new string. This is in case the user did not enter uniform
            # spacing in their list of outcomes
            outcomes = "".join(args[1:])
            # Split all outcomes into a list
            outcomes_list = outcomes.split(',')
            percentage = 1
            # For each outcome entered, convert the item to a number and try to look it up in the dictionary
            for outcome in outcomes_list:
                if outcome == '':
                    await message.channel.send('You did not enter a number. Use something like **!gamble 1,1,1,1**')
                    return
                # Check if there is an exclamation mark in front of each outcome. If so, the probability should be
                # negated(1-p)
                negate = False
                if outcome[0] == '!':
                    negate = True
                    outcome = outcome[1:]
                # If we can't convert the number to an int, the user didn't enter the outcomes correctly
                try:
                    outcome = int(outcome)
                except Exception as e:
                    await message.channel.send('You did not enter a number. Use something like **!gamble 1,1,1,1**')
                    return
                # If the item doesn't exist in the dictionary, then the user entered something wrong
                try:
                    # If we do get the dictionary value, multiply it by our current percent chance to get the new chance
                    # If there was an !, negate the dictionary value
                    if negate:
                        percentage = percentage * (1 - percentages[outcome])
                    else:
                        percentage = percentage * percentages[outcome]
                except KeyError as k:
                    await message.channel.send("You did not enter a valid wheel number. Enter 1, 3, 5, 10, or 20")
                    return

            await message.channel.send('The chance of the wheel landing on ' + ', '.join(outcomes_list) + ' is **' +
                                       "{:.2f}".format(percentage * 100) + '%**')

    # Outputs recycle data for a given item and item quantity
    elif message_text.startswith('!recycle'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a command description
        if len(args) == 1:
            await message.channel.send('This command will display the recycle output for a given item. Use '
                                       '**!recycle [itemname] [itemquantity]**')
        else:
            # Try to convert the last word in the command to an int to test if the user entered an amount
            num_items = 1
            try:
                # If the user entered an amount, check if it is a valid amount
                num_items = int(args[-1])
                if args[-1] <= 0:
                    await message.channel.send('Please enter a valid number')
                item_name = ' '.join(args[1:-1])
            except Exception:
                item_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            item = get_string_best_match(item_name_list, item_name)

            if item is None:
                return 'Item not found'

            # Once we find the appropriate item, get its recycle data from the database
            sql = '''SELECT * FROM recycle WHERE item_name = ?'''
            cursor.execute(sql, (item,))
            item_data = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]
            # if we don't get any item data, the item cannot be recycled
            if not item_data:
                return item + ' cannot be recycled'

            # Output the recycling data. If an output has a drop chance, output its expected value for the number of
            # items being recycled
            title = 'Displaying recycling output for ' + str(num_items) + ' ' + item
            fields = {}
            for item in item_data:
                recycle_name = check_emoji(message.channel.guild.emojis, item[1])
                recycle_quantity = item[2]
                if recycle_quantity is None:
                    if item[3] is None:
                        recycle_quantity = 1 * num_items
                        recycle_text = str(recycle_name) + ' x' + str(recycle_quantity)
                    else:
                        recycle_percent = int(''.join(filter(str.isdigit, item[3]))) * num_items // 100
                        recycle_text = str(recycle_name) + ' x' + str(recycle_percent) + '(' + item[3] + ')'
                else:
                    recycle_quantity = int(''.join(filter(str.isdigit, recycle_quantity))) * num_items
                    recycle_text = str(recycle_name) + ' x' + str(recycle_quantity)
                fields[recycle_text] = "\n\u200b"

            embed = format_embed(fields, title, item_url, None, item_img, None)
            await message.channel.send(embed=embed)

    # Checks pop of frequented servers if no server argument, and searches for a specific server if specified
    elif message_text.startswith('!serverpop'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, the user did not enter a server argument
        if len(args) == 1:
            # Search the specific servers we frequent
            await message.channel.send('Rustafied Trio currently has ' + server_pop(
                'https://www.battlemetrics.com/servers/rust/2634280') + ' players online\n'
                                                                        'Bloo Lagoon currently has ' + server_pop(
                'https://www.battlemetrics.com/servers/rust/3461363') + ' players online\n\n'
                                                                        'For specific server pop, use **!serverpop ['
                                                                        'servername]**')
            # If there is a server argument, add any arguments after !serverpop to the server name
        else:
            server_name = ""
            for i in args:
                if i == args[0]:
                    pass
                else:
                    if server_name == "":
                        server_name = i.capitalize()
                    else:
                        server_name = server_name + " " + i.capitalize()
            # Navigate to the specific server search requested
            server_http = server_name.replace(' ', '%20')
            server_http = server_http.replace('&', '%26')
            server_http = server_http.replace('?', '%3F')
            bm_url = 'https://battlemetrics.com/servers/rust?q=' + server_http + '&sort=rank'
            bm_html = get_html(bm_url)
            # Find the table containing the search results
            server_table = bm_html.find('table', {"class": "css-1yjs8zt"})
            # Get all children of the table
            entries = server_table.find('tbody').contents
            servers = []
            # Omit any results not containing a link
            # This mitigates the style child of the tbody
            for i in entries:
                if i.find('a'):
                    servers.append(i.find('a'))
            # Find the best match given the new list of servers and all search terms
            best_match = get_best_match(servers, server_name)
            # If get_best_match returns an empty string, there was no matching server
            if best_match == '':
                await message.channel.send('Server not found')
            # If we did find a server, get the link from the html element and get its pop via server_pop
            else:
                link = best_match['href']
                serv_name = best_match.text
                url = 'https://battlemetrics.com' + link
                await message.channel.send(
                    serv_name + ' currently has ' + server_pop(url) + ' players online')

    elif message_text.startswith('!binds'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is output a command description
        if len(args) == 1:
            embed = discord.Embed()
            embed.add_field(name="**!binds commands**", value="Displays all commands you can bind to a key"
                            , inline=True)
            embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
            embed.add_field(name="**!binds keys**", value="Displays all keys you can bind commands to", inline=True)
            embed.add_field(name="**!binds gestures**", value="Displays all gestures you can bind", inline=True)
            embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
            embed.add_field(name="**!binds popular**", value="Displays popular binds", inline=True)
            await message.channel.send("Use any of the below commands for information on various rust binds",
                                       embed=embed)
        # If there is a server argument, check if they entered 'keys' 'gestures' or 'commands'
        else:
            # Displays all console commands you can use
            if args[1].lower() == 'commands':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('C:/Users/Stefon/PycharmProjects/CamBot/bind_commands.txt') as file:
                    key_list = file.read().splitlines()
                    file.close()
                # Create embed for output
                embed = discord.Embed()
                # Get the first line and input it in the title, then put its subsequent line in the value of the embed
                start = 0
                for key in key_list:
                    if start % 2 == 0:
                        embed.add_field(name=key, value=key_list[start + 1], inline=False)
                    start += 1
                await message.channel.send(
                    'Displaying all commands you can bind in console. You can bind multiple commands to a key by '
                    'seperating them with a ;. Additionally, adding a + before a command will only activate it '
                    'while the key is held down', embed=embed)
            # Displays all keys currently bindable in Rust
            elif args[1].lower() == 'keys':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('C:/Users/Stefon/PycharmProjects/CamBot/bind_keys.txt') as file:
                    key_list = file.read().splitlines()
                    file.close()
                # Create embed for output
                embed = discord.Embed()
                # Get the first line and input it in the title, then put its subsequent line in the value of the embed
                start = 0
                for key in key_list:
                    if start % 2 == 0:
                        embed.add_field(name=key, value=key_list[start + 1], inline=False)
                    start += 1
                await message.channel.send("Displaying all supported keys you can bind commands to. In Rust console, "
                                           "enter **bind [key] [command]**\n", embed=embed)
            elif args[1].lower() == 'gestures':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('C:/Users/Stefon/PycharmProjects/CamBot/bind_gestures.txt') as file:
                    key_list = file.read().splitlines()
                    file.close()
                # Create embed for output
                embed = discord.Embed()
                gestures_text = "```"
                for key in key_list:
                    gestures_text += key + '\n'
                gestures_text += '```'
                await message.channel.send("Displaying all gestures. In Rust console, enter **bind [key] \" gesture"
                                           " [gestureName]\"** Make sure you include the quotes!\n" + gestures_text)
            elif args[1].lower() == 'popular':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('C:/Users/Stefon/PycharmProjects/CamBot/binds_popular.txt') as file:
                    key_list = file.read().splitlines()
                    file.close()
                # Create embed for output
                embed = discord.Embed()
                # Get the first line and input it in the title, then put its subsequent line in the value of the embed
                start = 0
                for key in key_list:
                    if start % 2 == 0:
                        embed.add_field(name=key, value=key_list[start + 1], inline=False)
                    start += 1
                await message.channel.send(
                    'Displaying the most popular binds', embed=embed)
            else:
                await message.channel.send('You did not enter a valid command. Use **!binds keys, gestures, '
                                           'commands, or popular**')

    # Output skin data from the MySQL server for a given item
    elif message_text.startswith('!skindata'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, the user did not enter a server argument
        if len(args) == 1:
            # Search the specific servers we frequent
            await message.channel.send(
                'This command will display price data for a specific skin. Use **!skindata [skinname]**\n'
                'All skin prices/dates are estimates, especially for skins released a long time ago')
        # If there is a server argument, add any arguments after !serverpop to the server name
        else:
            # If the user entered an item name, ensure it is all in one string and search for it in the database
            skin_name = ' '.join(args[1:])
            # Open a text file containing a list of all rust item names and find the best match
            with open('C:/Users/Stefon/PycharmProjects/CamBot/skins.txt') as file:
                skin_name_list = file.read().splitlines()
                file.close()
            best_skin = get_string_best_match(skin_name_list, skin_name)

            # Once we get the best matching item string, query the item's data from the SQL server. I originally
            # queried data matching the search term using the %like% keyword and then used best_match to get the
            # best item from the query's results. However, this often led to searches that didn't return any items
            # which is not what I wanted. So I decided to reverse them at the cost of performance
            sql = "SELECT * FROM skin WHERE skin_name = \"" + best_skin + "\""
            cursor.execute(sql)
            data = cursor.fetchall()[0]
            # Theoretically, there should always be a match but if there isn't exit the command and let the user know
            if not data:
                await message.channel.send('No skin data found for ' + best_skin + '. Use **!skindata [skinname]**\n')
                return

            # Once we have a best match, get the item's name url, initial price, and initial date
            name = data[0]
            skin_url = data[1]
            skin_initial_price = data[2]
            skin_initial_date = data[3]
            skin_type = data[4]
            skin_initial_date = skin_initial_date.split('-')
            skin_initial_date = skin_initial_date[1] + '-' + skin_initial_date[2] + '-' + skin_initial_date[0]
            skin_img = data[5]
            # Get the current price and an image for the item
            market = Market("USD")
            current_price = market.get_lowest_price(name, AppID.RUST)
            # Some skins may be added to the database before they are able to be listed due to steam's trading cooldown.
            # In this case there will be no current price and thus we should tell the user to wait for the item to be
            # able to be listed
            if not current_price:
                await message.channel.send(name + ' has no market price data at the moment. This probably means '
                                                  'the skin came out this week and cannot be placed on the market'
                                                  ' at this time.')
                return
            # Attempt to get the percent change, and if we divide by 0 somehow, just set the percent to 0
            try:
                percent_change = "{:.2f}".format(((current_price - skin_initial_price) / skin_initial_price) * 100)
            except ZeroDivisionError:
                percent_change = 0

            # Dipsplay the data and an image for the given item
            title = 'Displaying skin data for ' + name
            fields = {}
            fields['Release Date'] = skin_initial_date
            fields['Initial Price'] = '$' + str(skin_initial_price)
            fields['Current Price'] = '$' + str(current_price)
            fields['Price Difference'] = '$' + '{0:.2f}'.format(current_price - skin_initial_price)
            fields['Percent Change'] = str(percent_change) + '%'
            fields['Skin For'] = skin_type
            embed = format_embed(fields, title, skin_url, None, skin_img, None)
            await message.channel.send(embed=embed)


    # Print out the latest news regarding Rust's future update
    # This is used to return news whenever the website updates
    elif message_text.startswith('!rustnews'):
        # Navigate to Rustafied.com and get the title and description of the new article
        title, desc = get_news('https://rustafied.com')
        # Embed a link to the site with the retrieved title and description
        embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
        await message.channel.send('Here is the newest Rustafied article:', embed=embed)

    # Outputs a link to of the newest rust devblog. I am using an xml parser to scrape the rss feed as the
    # website was JS rendered and I could not get selerium/pyqt/anything to return all of the html that I needed
    elif message_text.startswith('!devblog'):
        title, devblog_url, desc = get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')
        embed = discord.Embed(title=title, url=devblog_url, description=desc)
        await message.channel.send('Newest Rust Devblog:', embed=embed)

    # Ouputs the drop table of a certain loot source
    elif message_text.startswith('!droptable'):
        args = message_text.split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            embed = discord.Embed()
            # Get all crate names from the sql server and display them
            sql = '''SELECT DISTINCT crate_name FROM droptable'''
            cursor.execute(sql)
            crates = list(i[0] for i in cursor.fetchall())
            embed_value = '\n'.join(crates)
            embed.add_field(name="\n\u200b", value=embed_value, inline=True)
            await message.channel.send('This command will display all items dropped from any of the following loot'
                                       ' sources along with their respective drop percentages:\n', embed=embed)
        # If the user enters a table name, search for it
        else:
            # Rejoin all args after !droptable to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_container = get_string_best_match(item_name_list, container_name)

            sql = '''SELECT * FROM droptable WHERE crate_name = ? ORDER BY percent_chance DESC'''
            cursor.execute(sql, (best_container,))
            rows = cursor.fetchall()

            if not rows:
                await message.channel.send(best_container + ' has no drop table')

            str_items = []
            for row in rows:
                str_items.append(row[1].ljust(28) + '\t' + str(row[2]).rjust(6) + '%')

            table_lines = format_text(str_items, 3)
            await message.channel.send('Displaying drop table for **' + best_container + '**:\n')
            # For each line we are trying to output, check if adding it would put us close to the message length
            # limit. If we are approaching it, post the current string and start a new one
            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await message.channel.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await message.channel.send('```' + output_msg + '```')

    # Posts a random picture from a given folder
    elif message_text.startswith('!campic'):
        img_path = 'C:/Users/Stefon/PycharmProjects/CamBot/Cam/'
        pics = []
        # Get the filenames of all images in the directory
        for fileName in os.listdir(img_path):
            pics.append(fileName)

        # Select a random filename from the list and upload the corresponding image
        rand_pic = random.choice(pics)
        file = discord.File(img_path + rand_pic, filename=rand_pic)
        await message.channel.send(file=file)


    # Output all loot sources that give a certain item
    elif message_text.startswith('!lootfrom'):
        args = message_text.split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display all loot sources that drop a certain item, along '
                                       'with their respective percentages. Use **!lootfrom [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            # Rejoin all args after !droptable to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, container_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            sql = '''SELECT * FROM droptable WHERE item_name = ? ORDER BY percent_chance DESC'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()

            if not rows:
                await message.channel.send(best_item + ' has no loot sources')
                return

            str_items = {}
            for row in rows:
                str_items[row[0]] = (str(row[2]) + '%')

            embed_title = 'Displaying drop percentages for ' + best_item
            embed = format_embed(str_items, embed_title, item_url, None, item_img, None)
            await message.channel.send(embed=embed)

    # Displays all stats pertaining to the item the user searches for
    elif message_text.startswith('!stats'):
        args = message_text.split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display all stats corresponding to a given item. Use **!stats'
                                       ' [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            search_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, search_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]
            title = 'Displaying item stats for ' + best_item

            sql = '''SELECT * FROM item_stats WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            stats = cursor.fetchall()

            # Get additional item stats from the item table and add them to the embed if they are not null
            sql = '''SELECT item_identifier, stack_size, despawn_time, health, description 
                    FROM items WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            general_stats = cursor.fetchall()[0]
            names = cursor.description

            desc = general_stats[-1]
            fields = {}
            for i in range(len(general_stats[:-1])):
                if general_stats[i]:
                    fields[names[i][0].replace('_', ' ').title()] = general_stats[i]

            # If the html returned is null, then there are no stats for the item
            if stats is None:
                await message.channel.send(best_item + ' has no stats')
                return

            for stat in stats:
                fields[stat[1]] = stat[2]
            embed = format_embed(fields, title, item_url, desc, item_img, None)
            await message.channel.send(embed=embed)

    elif message_text.startswith('!repair'):
        args = message_text.split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display the repair cost for a given item. Use **!repair'
                                       ' [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            search_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = get_string_best_match(item_name_list, search_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            sql = '''SELECT * FROM repair_data WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            repair_data = cursor.fetchall()

            sql = '''SELECT * FROM repair_cost WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            repair_costs = cursor.fetchall()

            embed_title = 'Displaying repair cost for ' + best_item
            fields = {}
            embed_text = ''
            for cost in repair_costs:
                material_name = cost[1]
                quantity = cost[2]
                emoji = check_emoji(message.channel.guild.emojis, material_name)

                embed_text += str(emoji) + ' x' + str(quantity) + '\n'
            fields['Repair Cost'] = embed_text

            if repair_data:
                repair_data = repair_data[0]
                fields['Condition Loss'] = repair_data[1]
                fields['Blueprint Required?'] = repair_data[2]

            embed = format_embed(fields, embed_title, item_url, None, item_img, None)
            # Output the item's repair data as an embed
            await message.channel.send(embed=embed)

    # Outputs the most efficient furnace ratios for a specific furnace and ore type
    elif message_text.startswith('!furnaceratios'):
        args = message_text.split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display the appropriate furnace ratio for the furnace and '
                                       'ore type specified. Use **!furnaceratios [small/large] [metal/sulfur]**')

        else:
            # Check if the user entered too many or too few arguments
            if len(args) == 3:
                # If set the size to whatever size the user entered. This is used to find the appropriate images
                if args[1] == 'large':
                    furnace_size = 'lf'
                elif args[1] == 'small':
                    furnace_size = 'sf'
                # If the user didn't enter large or small, then their input is invalid
                else:
                    await message.channel.send(
                        'You entered an invalid furnace size. Please enter \'small\' or \'large\'')
                    return
                # Assign whatever ore the user entered to ore_type, ensuring 'metal' or 'sulfur' were entered
                if args[2] == 'metal' or args[2] == 'sulfur':
                    ore_type = args[2]
                else:
                    await message.channel.send('The given ore type is invalid. Please enter \'sulfur\' or \'metal\'')
                    return
                # Get all images in the Rust folder containing the appropriate furnace size and ore type
                await message.channel.send('Displaying ' + ore_type + ' ratios for a ' + args[1] + ' furnace:\n\n')
                img_path = 'C:/Users/Stefon/PycharmProjects/CamBot/Rust/'
                for img in os.listdir(img_path):
                    if furnace_size in img[0:2]:
                        if ore_type in img:
                            file = discord.File(img_path + img, filename=img)
                            embed = discord.Embed()
                            # Get the wood amount from the image name
                            temp_amts = re.findall(r"[-+]?\d*\.\d+|\d+", img)
                            wood_amt = int(float(temp_amts[0]) * 1000)
                            ore_amt = temp_amts[1]
                            # Wood takes 2 seconds to smelt in any furnace. So the total time is wood * 2
                            time = strftime("%X", gmtime(wood_amt * 2))
                            # Output each appropriate image and the corresponding smelting data
                            img_text = '**' + str(wood_amt) + '** wood' + ' will smelt **' + str(ore_amt) + '** ' \
                                       + args[2] + ' and will take **' + time + '**'
                            embed.set_image(url="attachment://" + img)
                            await message.channel.send(img_text, file=file, embed=embed)


            elif len(args) > 3:
                await message.channel.send('You entered too many arguments. use !furnaceratios for proper syntax')
                return
            else:
                await message.channel.send('You entered too few arguments. Use !furnaceratios for proper syntax')
                return
    # Outputs how many explosives you can craft with x sulfur
    elif message_text.startswith('!sulfur'):
        args = message_text.split()
        # If len(args) is 1, the user didn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will output the amount of explosives you can sauce with a given '
                                       'sulfur amount. Use **!sulfur [sulfuramount]**')
        elif len(args) > 2:
            await message.channel.send('Too many arguments, please enter **!suflur [sulfuramount]**.'
                                       ' If you have gunpower, multiply the amount by 2 to get the amount of sulfur')
        else:
            num_sulf = -1
            try:
                num_sulf = int(args[-1])
            except Exception as e:
                pass
            # If the user entered an amount, check if it is a valid amount
            if num_sulf <= 0:
                await message.channel.send('Please enter a valid number')
            else:
                # If the user entered a valid amount, call craft_calc with the amount
                await message.channel.send('', embed=sulf_calc(num_sulf, message.channel.guild))

    # Displays the current list of rust items for sale, along with their prices
    elif message_text.startswith('!rustitems'):
        items, total_item_price = get_rust_items('https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        total_item_price = '$' + str("{:.2f}".format(total_item_price))
        # If the dictionary is empty, then the item store is having an error or is updating
        if not bool(items):
            await message.channel.send('Rust item store is not hot!!!')
        # If we have entries, format and display them
        else:
            # Display the first item we get in an embed
            embed = discord.Embed(title=items[0].n,
                                  url='https://store.steampowered.com/itemstore/252490/browse/?filter=All')
            embed.set_thumbnail(url=items[0].im)
            footer_text = 'Page 1/' + str(len(items))
            embed.set_footer(text=footer_text)
            pr_price = str(items[0].pr)
            embed.add_field(name='Item price', value=items[0].p, inline=True)
            embed.add_field(name='Predicted price(1yr)', value=pr_price, inline=True)
            msg = await message.channel.send(embed=embed)
            # Insert all other items into the SQL database with corresponding message and channel ids
            for item in items:
                try:
                    sql = "INSERT INTO item_store_messages (message_id, channel_id, item_name, starting_price, " \
                          "predicted_price, store_url) VALUES(?, ?, ?, ?, ?, ?)"
                    temp_pr = str(item.pr)
                    val = (msg.id, message.channel.id, item.n, item.p, temp_pr, item.im)
                    cursor.execute(sql, val)
                    connection.commit()
                except Exception as e:
                    pass
            # React to the message to set up navigation
            await msg.add_reaction('◀')
            await msg.add_reaction('▶')



    # Gets the recipe for a certain item
    elif message_text.startswith('!craftcalc'):
        # Split the input command into a list
        args = message_text.split()
        # If len(args) is 1, output a command description
        if len(args) == 1:
            await message.channel.send('This command will display the recipe for a given item. Use '
                                       '**!craftcalc [itemname] [itemquantity]**')
        else:
            # Try to convert the last word in the command to an int to test if the user entered an amount
            num_crafts = 1
            try:
                # If the user entered an amount, check if it is a valid amount
                num_crafts = int(args[-1])
                if args[-1] <= 0:
                    await message.channel.send('Please enter a valid number')
                item_name = ' '.join(args[1:-1])
            except Exception:
                item_name = ' '.join(args[1:])

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            item = get_string_best_match(item_name_list, item_name)

            if item is None:
                return 'Item not found'

            # Once we find the appropriate item, get its recycle data from the database
            sql = '''SELECT * FROM craftcalc WHERE item_name = ?'''
            cursor.execute(sql, (item,))
            ingredients = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # if we don't get any item data, the item cannot be recycled
            if not ingredients:
                return item + ' has no crafting recipe'

            sulfur_cost = 0
            craft_string = 'Recipe for ' + str(num_crafts) + ' ' + item
            fields = {}
            for ingredient in ingredients:
                output_number = int(ingredient[3])
                # Get quantity of materials, default to 1(if no text), if there is text strip the 'x' or 'ft' from the
                # text and convert it to an int so we can multiply by num_crafts
                quantity = ingredient[2]
                item_name = ingredient[1]
                item_emoji = check_emoji(message.channel.guild.emojis, item_name)
                total = (int(quantity) * int(num_crafts) // output_number)
                embed_text = str(item_emoji) + ' x' + str(total)
                fields[embed_text] = "\n\u200b"

                if item_name == 'Sulfur':
                    sulfur_cost += (int(quantity) * int(num_crafts) // output_number)
                elif item_name == 'Gunpowder':
                    sulfur_cost += (int(quantity * 2) * int(num_crafts) // output_number)
                elif item_name == 'Explosives':
                    sulfur_cost += (int(quantity * 110) * int(num_crafts) // output_number)

            footer_string = None
            # Check if the sulfur amount is > 0. If so, get the total sulfur amount
            if sulfur_cost > 0:
                footer_string = 'Total sulfur cost: ' + str(sulfur_cost)

            embed = format_embed(fields, craft_string, item_url, None, item_img, footer_string)
            await message.channel.send(embed=embed)


    # Tweet a message using tweepy
    elif message_text.startswith('!tweet'):
        msg = '@yvngalec @AidanT5 TEST TWEET YES'
        await message.channel.send(tweet(msg))

    # Get status of all servers the bot depends on with get_status
    elif message_text.startswith('!status'):
        statuses = get_status()
        embed = discord.Embed(title='Displaying staus of all dependent servers:')
        # Display statuses in an embed
        for status in statuses:
            embed.add_field(name=status, value=statuses[status], inline=False)

        await message.channel.send(embed=embed)

    elif message_text.startswith('!addemojis'):
        result = await add_emojis(message.channel.guild)
        await message.channel.send(result)

    elif message_text.startswith('!removeemojis'):
        result = await remove_emojis(message.channel.guild)
        await message.channel.send(result)
    elif message_text.startswith('!update'):
        tweet('Cambot is down for updates and will be available again in ~20 minutes.')
        output = cambot_updater.update_database()
        await message.channel.send(output)
    else:
        return

    command_end = timer()
    command = message_text.split()[0]
    command_time = command_end - command_start
    print(command + ' execution completed in ' + str(command_time) + ' seconds')
    cursor.execute("""INSERT INTO command_times(command_name, execution_time)
                        VALUES(?, ?);""", (command, command_time))
    connection.commit()


client.loop.create_task(check())
client.run(keys[0])
