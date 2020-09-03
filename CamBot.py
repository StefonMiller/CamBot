import calendar
import json
import math
import os
import random
import re
import urllib
from time import strftime, gmtime, time
from urllib.error import HTTPError
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
from discord.ext import commands

updated_devblog = False


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


CAMBOT_START_TIME = datetime.now()


# Gets the command prefix for the current server
# @Param message: Message containing the id of the server whose prefix we are looking up
# @Return: Prefix located in the server_prefix json file
def get_server_prefix(client, message):
    with open('server_prefixes.json', 'r') as f:
        prefixes = json.load(f)

    return prefixes[str(message.guild.id)]


# Get API keys from keys text file
with open('keys.txt') as f:
    keys = f.read().splitlines()
    f.close()

# Create Bot object and set the prefix for each server. Remove the default help command and make all commands case
# insensitive
client = commands.Bot(command_prefix=get_server_prefix, help_command=None, case_insensitive=True)

for filename in os.listdir('cogs/'):
    if filename.endswith('.py'):
        print('Loading ' + f'cogs.{filename[:-3]}')
        client.load_extension(f'cogs.{filename[:-3]}')


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


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
            item_status = check_for_updates('current_skins.txt', check_item)
        else:
            item_status = 0
        # Check if any of the corresponding text files were updated
        news_status = check_for_updates('current_news.txt', news_title)
        devblog_status = check_for_updates('current_devblog.txt', devblog_title)

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
            with open('skins.txt', "a") as file:
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
    try:
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
    except HTTPError:
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
    with open("cached_items.txt") as file:
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
        with open("cached_items.txt", 'w') as f:
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


# Generates a list of PIL images for a list of skins from the item store(No longer used)
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


def get_start_time():
    return CAMBOT_START_TIME


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


# Sets the prefix of the given server to '!'
# @Param guild: Guild whos prefix we are setting
# @Return: Success message
def set_default_prefix(guild):
    try:
        with open('server_prefixes.json', 'r') as f:
            prefixes = json.load(f)
    except Exception:
        pass

    prefixes[str(guild.id)] = '!'

    with open('server_prefixes.json', 'w') as f:
        json.dump(prefixes, f)

    return 'Prefix for Cambot set to \'!\'. To change it, use **!changeprefix**'


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
                with open('leavestrings.txt') as leave:
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
            with open('joinstrings.txt') as join:
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
    await guild.text_channels[0].send('OOOO CAMBOT COMING IN HOT SPICY DICEYYY')
    # Initialize emojis and server prefix whenever Cambot is added to the server
    emoji_result = await add_emojis(guild)
    prefix_result = set_default_prefix(guild)
    # Output result of initialization to first text channel in server
    await guild.text_channels[0].send(emoji_result + '\n' + prefix_result)


@client.event
async def on_guild_remove(guild):
    # Remove the server's prefix from the json file when Cambot is removed
    with open('server_prefixes.json', 'r') as f:
        prefixes = json.load(f)

    del prefixes[str(guild.id)]

    with open('server_prefixes.json', 'w') as f:
        json.dump(prefixes, f)

if __name__ == "__main__":
    pass

client.loop.create_task(check())
client.run(keys[0])
