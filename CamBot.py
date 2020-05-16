import os
import random
import re
import textwrap
import urllib
from time import strftime, gmtime
import discord
from steam_community_market import Market, AppID
from requests import get
from contextlib import closing
from bs4 import BeautifulSoup
import tweepy
from datetime import datetime, date, timedelta
from fuzzywuzzy import fuzz
import mysql.connector
import asyncio
import string

# Get API keys from keys text file
with open('C:/Users/Stefon/PycharmProjects/CamBot/keys.txt') as f:
    keys = f.read().splitlines()
    f.close()
# Create client object for discord integration
client = discord.Client()

# Connect to the MySQL server and get the item corresponding to the best_skin found above
with open('C:/Users/Stefon/PycharmProjects/CamBot/serverinfo.txt') as f:
    info = f.read().splitlines()
    f.close()
cursor = None
try:
    connection = mysql.connector.connect(
        host=info[0],
        database=info[1],
        user=info[2],
        password=info[3]
    )

    if connection.is_connected():
        db_Info = connection.get_server_info()
        cursor = connection.cursor()
except Exception as e:
    pass


# Background task used to check for website changes
async def check():
    await client.wait_until_ready()
    while not client.is_closed():
        print('Checking for site changes...')
        # Get the first skin in the rust item store to check for changes
        items, total_item_price = get_rust_items('https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        item_name = next(iter(items))

        # Get the title of the newest article on rustafied to check for changes
        news_title, news_desc = get_news('https://rustafied.com')

        # Get the title of the newest devblog to check for updates
        devblog_title, devblog_url, desc = get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')

        # Check if any of the corresponding text files were updated
        item_status = check_for_updates('C:/Users/Stefon/PycharmProjects/CamBot/current_skins.txt', item_name)
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
                await update_items(channel_list, items, total_item_price)
                print('Posted item store update')
            if news_status == 1:
                await post_rust_news_update(channel_list, news_title, news_desc)
                print('Posted Rustafied news update')
            if devblog_status == 1:
                await post_devblog_update(channel_list, devblog_title, devblog_url, desc)
                print('Posted devblog update')
        else:
            print('No changes found...')
            pass
        await asyncio.sleep(900)


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
        item_http = item.replace(' ', '%20')
        item_http = item_http.replace('&', '%26')
        item_url = 'https://steamcommunity.com/market/listings/' + '252490' + '/' + item_http
        item_price = float(items[item][1:])
        try:
            sql = "INSERT INTO skin (skin_name, link, initial_price, release_date) VALUES(%s, %s, %s, %s)"
            val = (item, item_url, item_price, today)
            cursor.execute(sql, val)
            connection.commit()
            print('Successfully inserted ' + item)
            # Once we insert the items, we know it is not a duplicate entry and can insert the name into our text file
            # containing all skin names
            with open('C:/Users/Stefon/PycharmProjects/CamBot/skins.txt', "a") as file:
                file.write(item + '\n')
                print('Added ' + item + ' to text file')
        except Exception as e:
            print('Duplicate entry, skipping ' + item + '...')

    return


# Announces the rust item store has updated, displays all item data, and then calls insert_items
# @Param channels: List of channels to post the announcement to
# @Param items: all items currently in the store
# @Param total_price: Total price of all items
async def update_items(channels, items, total_price):
    total_item_price = '$' + str("{:.2f}".format(total_price))
    # If the dictionary is empty, then the item store is having an error or is updating
    if not bool(items):
        pass
    # If we have entries, format and display them
    else:
        embed = discord.Embed()
        # Format the strings for display in an embed
        for item in items:
            item_text = '**' + item + '**'
            embed.add_field(name='**' + item_text + '**', value=items[item], inline=False)
        embed.add_field(name='**Total Price:** ', value=total_item_price, inline=False)
        item_str = 'The Rust item store has updated with new items: ' \
                   + 'https://store.steampowered.com/itemstore/252490/browse/?filter=All' + '\n\n'
        for channel in channels:
            await channel.send(item_str, embed=embed)
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
    return


# Make a post in channel announcing the new rust news on Rustafied
# @Param channels: List of channels to post the announcement to
# @Param title: Title of news article
# @Param desc: Description of news article
async def post_rust_news_update(channels, title, desc):
    embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
    for channel in channels:
        await channel.send('Rustafied has published a new news article', embed=embed)
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
# @Return: whether or not we were able to successfully connect to all servers
def get_status():
    # Attempt connection to each dependent server and if the status is not 200, return false
    import requests
    servers = [requests.head('https://www.battlemetrics.com/'), requests.head('https://rust.facepunch.com/blog/'),
               requests.head('https://www.rustlabs.com/'), requests.head('https://rustafied.com/')]

    for server in servers:
        if server.status_code == 200 or 301:
            pass
        else:
            return 'Serv ' + server.url + ' is NOT hot, status code alpha bravo ' + str(server.status_code) + '!!!'
    return 'All servs r hot n ready like little C\'s'


# Returns the crafting recipe for a certain item in the rustitem database
# @Param item_name: name of the item to get from the database
# @Param num_crafts: number of times to craft said item
# @Return: Total crafting cost for the requested item * num_crafts
def craft_calc(search_term, num_crafts):
    item_url = 'https://rustlabs.com/group=itemlist'
    item_html = get_html(item_url)
    # Get all item entries and use fuzzywuzzy to find the best match according to our list of search terms.
    # Originally I had implemented a system in which I used re.compile to get all items with at least 1 search term to
    # Reduce the amount of items returned, and then processed the resulting set against all search terms. However,
    # this led to a lot of bugs and was really bad in general. This solution is far better than my original
    item_list = item_html.find_all('span', {"class": "r-cell"})
    item = get_best_match(item_list, search_term)
    if item is None:
        return 'Item not found'
    else:
        item_link = item.parent['href']
        # Once we find the appropriate item, open its corresponding page and get the crafting data
        total_link = 'https://rustlabs.com' + item_link + '#tab=craft'
        craft_html = get_html(total_link)
        # Get the tr in which the recipe is stored
        try:
            recipe = craft_html.find('td', {"class": "item-cell"}).parent
        except Exception as e:
            return 'This item has no recipe'
        # Get the first td in the tr with a class title 'no-padding'
        ingredient_td = recipe.find('td', {"class": "no-padding"})
        if ingredient_td is None:
            return 'This item has no recipe'
        else:
            # Find all ingredients in the first row we found
            ingredients = ingredient_td.find_all('a', {"class": "item-box"})
            # Get the ingredient name and quantity out of each ingredient and put them in a list. Additionally,
            # we have to get the output of the recipe(ex: 1 gunpowder craft gives you 10 gunpowder) in order to
            # make the numbers correct
            output_img = craft_html.find('img', {"class": "blueprint40"})
            output_number = output_img.find_next_sibling()
            if output_number.text == '':
                output_number = 1
            else:
                output_number = int(''.join(filter(str.isdigit, output_number.text)))
            craft_name = craft_html.find('h1').text
            craft_string = 'Recipe for ' + str(num_crafts) + ' **' + craft_name + '**:\n'
            for ingredient in ingredients:
                # Get quantity of materials, default to 1(if no text), if there is text strip the 'x' or 'ft' from the
                # text and convert it to an int so we can multiply by num_crafts
                quantity = 1
                if ingredient.text == '':
                    pass
                else:
                    quantity = int(''.join(filter(str.isdigit, ingredient.text)))
                total = int((quantity * num_crafts) / output_number)
                craft_string += '\t' + str(total) + ' ' + str(ingredient.find('img')['alt']) + '\n'

            return craft_string


# Returns the best item in i_list matching term. Used for craftcalc and serverpop commands
# @Param i_list: list of items that have the text attirbute for comparison
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
        else:
            pass
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
def tweet(msg, pic):
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
        api.update_status(msg)
    else:
        media = api.media_upload(pic)
        tweet = msg
        post_result = api.update_status(status=tweet, media_ids=[media.media_id])

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
    item_dict = {}
    total_price = 0
    for i in item_divs:
        # Get div containing item name and store its text attribute
        item_name_div = i.find('div', {"class": "item_def_name ellipsis"})
        item_name = item_name_div.text
        # Get div containing item price and store its text attribute
        item_price_div = i.find('div', {"class": "item_def_price"})
        # Convert the price to a double for addition and store it in the total price var
        item_price = "".join(i for i in item_price_div.text if 126 > ord(i) > 31)
        item_price_in_double = float(item_price[1:])
        total_price += item_price_in_double
        item_dict[item_name] = item_price
    return item_dict, total_price


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
def get_html(url):
    with closing(get(url, stream=True)) as resp:
        content_type = resp.headers['Content-Type'].lower()
        if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
            html = BeautifulSoup(resp.content, 'html.parser')
            return html
        else:
            return ''


# For an input amount of sulfur, display how many rockets, c4, etc you can craft
# @Param sulfur: How much sulfur the user has
# @Return: A string containing how many of each explosive they can craft
def sulf_calc(sulfur):
    rocket_sulf = 1400
    explo_sulf = 25
    satchel_sulf = 480
    c4_sulf = 2200
    sulf_string = 'With **' + str(sulfur) + '** sulfur, you can craft:\n' + '\t**' + str(sulfur // rocket_sulf) + \
                  '** Rockets with **' + str(sulfur % rocket_sulf) + '** sulfur left over\n' + '\t**' + \
                  str(sulfur // explo_sulf) + '** Explosive 5.56 with **' + str(sulfur % explo_sulf) + \
                  '** sulfur left over\n' + '\t**' + str(sulfur // satchel_sulf) + '** Satchel Charges with **' \
                  + str(sulfur % satchel_sulf) + '** sulfur left over\n' + '\t**' + str(sulfur // c4_sulf) + \
                  '** C4 with **' + str(sulfur % c4_sulf) + '** sulfur left over'
    return sulf_string


# Return the recycle output for a given item
# @Param search_term item user is searching for
# @Param num_items number of items the user is recycling
# @Return the output of recycling num_items search_terms
def recycle(search_term, num_items):
    item_url = 'https://rustlabs.com/group=itemlist'
    item_html = get_html(item_url)
    # Get all item entries and use fuzzywuzzy to find the best match according to our list of search terms.
    # Originally I had implemented a system in which I used re.compile to get all items with at least 1 search term to
    # Reduce the amount of items returned, and then processed the resulting set against all search terms. However,
    # this led to a lot of bugs and was really bad in general. This solution is far better than my original
    item_list = item_html.find_all('span', {"class": "r-cell"})
    item = get_best_match(item_list, search_term)
    if item is None:
        return 'Item not found'
    else:
        item_link = item.parent['href']
        # Once we find the appropriate item, open its corresponding page and get the recycle data
        total_link = 'https://rustlabs.com' + item_link + '#tab=recycle'
        recycle_html = get_html(total_link)
        recycle_name = recycle_html.find('h1').text
        # Get all resource/component outputs from the recycle output and their respective drop chances
        try:
            recycle_output = recycle_html.find('div', {"data-name": "recycle"}).find('td',
                                                                                     {"class": "no-padding"}).find_all(
                'a')
        except Exception as e:
            return recycle_name + ' cannot be recycled'

        # Output the recycling data. If an output has a drop chance, output its expected value for the number of items
        # being recycled
        recycle_text = 'Displaying recycling output for ' + str(num_items) + ' **' + recycle_name + '**:\n'
        for output in recycle_output:
            recycle_name = output.find('img')['alt']
            recycle_quantity = output.find('span').text
            if recycle_quantity == '':
                recycle_quantity = 1 * num_items
                recycle_text += '\t' + str(recycle_quantity) + ' ' + recycle_name + '\n'
            elif '%' in recycle_quantity:
                recycle_percent = int(''.join(filter(str.isdigit, recycle_quantity))) * num_items // 100
                recycle_text += '\tYou should expect to get ' + str(
                    recycle_percent) + ' ' + recycle_name + '(' + recycle_quantity + ' chance for each item)\n'
            else:
                recycle_quantity = int(''.join(filter(str.isdigit, recycle_quantity))) * num_items
                recycle_text += '\t' + str(recycle_quantity) + ' ' + recycle_name + '\n'

        return recycle_text


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


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
                # If an exception is raised when trying to send a message, then squaddies is not a text channel
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
async def on_message(message):
    # Ignore messages from the bot to avoid infinite looping
    if message.author == client.user:
        return
    # Dont bother processing a message if it isn't a command
    if not message.content.lower().startswith('!'):
        return

    # TODO Finish command list
    # Display all commands. This was originally a function call but I didn't really see the point if using embeds
    if message.content.lower().startswith('!cambot'):
        embed = discord.Embed()
        embed.add_field(name="**!craftcalc**", value="Outputs the recipe of an item", inline=False)
        embed.add_field(name="**!status**", value="Outputs the current status of CamBot's dependent servers",
                        inline=False)
        embed.add_field(name="**!serverpop**", value="Outputs the current pop of any server", inline=False)
        embed.add_field(name="**!devblog**", value="Posts a link to the newest devblog with a short summary",
                        inline=False)
        embed.add_field(name="**!rustnews**", value="Posts a link to the latest news on Rust's development info",
                        inline=False)
        embed.add_field(name="**!rustitems**", value="Displays all items on the Rust store along with prices",
                        inline=False)
        embed.add_field(name="**!droptable**", value="Outputs the drop table for a crate/NPC", inline=False)
        embed.add_field(name="**!lootfrom**", value="Outputs drop rates for a specific item", inline=False)
        embed.add_field(name="**!sulfur**", value="Outputs how many explosives you can craft with a specific sulfur "
                                                  "amount", inline=False)
        embed.add_field(name="**!furnaceratios**", value="Shows the most efficient furnace ratios for a given furnace "
                                                         "and ore type", inline=False)
        embed.add_field(name="**!smelting**", value="Shows smelting data for a given item", inline=False)
        embed.add_field(name="**!campic**", value="Posts a HOT pic of Cammy", inline=False),
        embed.add_field(name="**!recycle**", value="Displays the output of recycling an item", inline=False),
        embed.add_field(name="**!skindata**", value="Displays skin price data for an item", inline=False)
        embed.add_field(name="**!stats**", value="Outputs the stats of a given item(weapon, armor, etc)", inline=False)
        embed.add_field(name="**!repair**", value="Outputs the cost to repair an item", inline=False)
        embed.add_field(name="**!binds**", value="Displays all supported commands to bind", inline=False)
        embed.add_field(name="**!gamble**", value="Displays bandit camp wheel percentages and calculates the "
                                                  "chance of a certain outcome occuring", inline=False)
        await message.channel.send('Here is a list of commands. For more info on a specific command, use '
                                   '**![commandName]**\n', embed=embed)

    # Displays bandit camp wheel percentages and the chance of a certain event happening
    elif message.content.lower().startswith('!gamble'):
        # Split the input command into a list
        args = message.content.lower().split()
        # If len(args) is 1, output a the chances for each wheel outcome and display the wheel image
        if len(args) == 1:
            outcome_text = "```1\t\t\t\t48%\n" \
                           "3\t\t\t\t24%\n" \
                           "5\t\t\t\t16%\n" \
                           "10\t\t\t\t8%\n" \
                           "20\t\t\t\t4%```"
            await message.channel.send('Displaying the percentages of hitting each number on the bandit camp wheel. '
                                       'Use **!gamble [num],[num],[num],etc** to get the chance for a series of '
                                       'outcomes to occur\n' + outcome_text)
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
                # If we can't convert the number to an int, the user didn't enter the outcomes correctly
                try:
                    outcome = int(outcome)
                except Exception as e:
                    await message.channel.send('You did not enter a number. Use something like **!gamble 1,1,1,1**')
                    return
                # If the item doesn't exist in the dictionary, then the user entered something wrong
                try:
                    # If we do get the dictionary value, multiply it by our current percent chance to get the new chance
                    percentage = percentage * percentages[outcome]
                except KeyError as k:
                    await message.channel.send("You did not enter a valid wheel number. Enter 1, 3, 5, 10, or 20")
                    return

            await message.channel.send('The chance of the wheel landing on ' + str(outcomes_list) + ' is **' +
                                       "{:.2f}".format(percentage * 100) + '%**')

    # Outputs recycle data for a given item and item quantity
    elif message.content.lower().startswith('!recycle'):
        # Split the input command into a list
        args = message.content.lower().split()
        # If len(args) is 1, output a command description
        if len(args) == 1:
            await message.channel.send('This command will display the recycle output for a given item. Use '
                                       '**!recycle [itemname] [itemquantity]**')
        else:
            # Get the item name and quantity from the user input
            recycle_name = []
            for i in args:
                # Omit the !recycle command and the item number from the item name
                if i == args[0] or i == args[-1]:
                    pass
                else:
                    recycle_name.append(i)
            # Try to convert the last word in the command to an int to test if the user entered an amount
            try:
                # If the user entered an amount, check if it is a valid amount
                args[-1] = int(args[-1])
                if args[-1] <= 0:
                    await message.channel.send('Please enter a valid number')
                else:
                    # If the user entered a valid amount, call recycle with the amount
                    recycle_num = args[-1]
                    await message.channel.send(recycle(' '.join(recycle_name), recycle_num))
            # If the user didn't enter an amount, add the last word to the item name and call recycle with 1 as
            # the amount
            except Exception as e:
                if not recycle_name:
                    recycle_name.append(i)
                await message.channel.send(recycle(' '.join(recycle_name), 1))

    # Checks pop of frequented servers if no server argument, and searches for a specific server if specified
    elif message.content.lower().startswith('!serverpop'):
        # Split the input command into a list
        args = message.content.lower().split()
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
            serv_name = ""
            for i in args:
                if i == args[0]:
                    pass
                else:
                    if serv_name == "":
                        serv_name = i.capitalize()
                    else:
                        serv_name = serv_name + " " + i.capitalize()
            # Navigate to the specific server search requested
            bm_url = 'https://battlemetrics.com/servers/rust?q=' + serv_name + '&sort=rank'
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
            best_match = get_best_match(servers, serv_name)
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

    elif message.content.lower().startswith('!binds'):
        # Split the input command into a list
        args = message.content.lower().split()
        # If len(args) is output a command description
        if len(args) == 1:
            embed = discord.Embed()
            embed.add_field(name="**!binds commands**", value="Displays all commands you can bind to a key"
                            , inline=False)
            embed.add_field(name="**!binds keys**", value="Displays all keys you can bind commands to", inline=False)
            embed.add_field(name="**!binds gestures**", value="Displays all gestures you can bind", inline=False)
            embed.add_field(name="**!binds popular**", value="Displays popular binds", inline=False)
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
                        embed.add_field(name=key, value=key_list[start+1], inline=False)
                    start += 1
                await message.channel.send("Displaying all supported keys you can bind commands to. In Rust console, "
                                           "enter **bind [key] [command]**\n",  embed=embed)
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
    elif message.content.lower().startswith('!skindata'):
        # Split the input command into a list
        args = message.content.lower().split()
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
                await message.channel.send('No skin data found for the given skin. Use **!skindata [skinname]**\n')
                return

            # Once we have a best match, get the item's name url, initial price, and initial date
            name = data[0]
            skin_url = data[1]
            skin_initial_price = data[2]
            skin_initial_date = data[3]
            # Rearrange the date format for US convenience
            skin_initial_date = skin_initial_date.strftime("%m-%d-%Y")
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
            skin_html = get_html(skin_url)
            # Attempt to get the percent change, and if we divide by 0 somehow, just set the percent to 0
            try:
                percent_change = "{:.2f}".format(((current_price - skin_initial_price) / skin_initial_price) * 100)
            except ZeroDivisionError:
                percent_change = 0

            # Dipslay the data and an image for the given item
            img_div = skin_html.find('div', {"class": "market_listing_largeimage"}).find('img')['src']
            embed = discord.Embed()
            embed.add_field(name="Item name", value=name, inline=False)
            embed.add_field(name="Release date", value=skin_initial_date, inline=False)
            embed.add_field(name="Initial price", value='$' + str(skin_initial_price), inline=False)
            embed.add_field(name="Current price", value='$' + str(current_price), inline=False)
            embed.add_field(name="Percent change", value=str(percent_change) + '%', inline=False)
            embed.add_field(name='Steam market link', value=skin_url, inline=False)
            embed.set_image(url=img_div)
            await message.channel.send('Displaying skin data for **' + name + '**', embed=embed)



    # Print out the latest news regarding Rust's future update
    # This will be used to return news whenever the website updates
    elif message.content.lower().startswith('!rustnews'):
        # Navigate to Rustafied.com and get the title and description of the new article
        title, desc = get_news('https://rustafied.com')
        # Embed a link to the site with the retrieved title and description
        embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
        await message.channel.send('This will be used in the future to make a discord post whenever Rustafied updates '
                                   'with news', embed=embed)

    # Outputs a link to of the newest rust devblog. I am using an xml parser to scrape the rss feed as the
    # website was JS rendered and I could not get selerium/pyqt/anything to return all of the html that I needed
    elif message.content.lower().startswith('!devblog'):
        title, devblog_url, desc = get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')
        embed = discord.Embed(title=title, url=devblog_url, description=desc)
        await message.channel.send('Newest Rust Devblog:', embed=embed)

    # Ouputs the drop table of a certain loot source
    elif message.content.lower().startswith('!droptable'):
        args = message.content.lower().split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            embed = discord.Embed()
            embed.add_field(name="APC Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Locked Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Outpost Scientist", value="\n\u200b", inline=True)
            embed.add_field(name="Bandit Camp Guard", value="\n\u200b", inline=True)
            embed.add_field(name="Medical Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Primitive Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Barrel", value="\n\u200b", inline=True)
            embed.add_field(name="Military Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Ration Box", value="\n\u200b", inline=True)
            embed.add_field(name="Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Military Tunnel Scientist", value="\n\u200b", inline=True)
            embed.add_field(name="Roaming Scientist", value="\n\u200b", inline=True)
            embed.add_field(name="Elite Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Mine Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Sunken Chest", value="\n\u200b", inline=True)
            embed.add_field(name="Food Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Minecart", value="\n\u200b", inline=True)
            embed.add_field(name="Sunken Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Heavy Scientist", value="\n\u200b", inline=True)
            embed.add_field(name="Oil Barrel", value="\n\u200b", inline=True)
            embed.add_field(name="Supply Drop", value="\n\u200b", inline=True)
            embed.add_field(name="Helicopter Crate", value="\n\u200b", inline=True)
            embed.add_field(name="Oil Rig Scientist", value="\n\u200b", inline=True)
            embed.add_field(name="Tool Box", value="\n\u200b", inline=True)
            await message.channel.send('This command will display all items dropped from any of the following loot'
                                       ' sources along with their respective drop percentages:\n', embed=embed)
        # If the user enters a table name, search for it
        else:
            # Get all tr's that hold info on loot containers
            loot_container_html = get_html('https://rustlabs.com/group=containers')
            # Unfortunately there are a couple loot containers on a different page, so other_html is for the edge case
            # in which a user searches for one of those
            other_html = get_html('https://rustlabs.com/group=else')
            container_links = []

            # From the list of tr's, get their links and put them in a list
            containers = loot_container_html.find_all('td', {"class": "left"})
            for container in containers:
                container_links.append(container.find('a'))

            # Get the other list of tr's on the else page. I could filter these based on the 5 entries I know are needed
            # but I figure the search algorithm will never match them anyway so there is no harm appending every
            # entry into the list
            other_containers = other_html.find_all('td', {"class": "left"})
            for other_container in other_containers:
                container_links.append(other_container.find('a'))

            # Rejoin all args after !droptable to pass it onto get_best_match
            container_name = ' '.join(args[1:])

            # Once we get the best match, display all droppable items and their drop chances
            # Start by connecting to the loot table page and retrieving a list of the items
            best_container = get_best_match(container_links, container_name)
            container_url = 'https://www.rustlabs.com' + best_container['href'] + '#tab=content;sort=3,1,0'
            container_html = get_html(container_url)
            # Hack for loot tables that have HP values(scientists, etc)
            container_table = container_html.find('table', {"class": "table w100 olive sorting"})
            container_table_body = container_table.find('tbody')
            # For each row in the tbody, insert columns 1 and 4 as an entry into an output string. I wanted to
            # use an embed for its nice columns(which discord doesn't support as of yet) but a lot of the time there
            # were more than 25 entries which is discord's max for an embed
            rows = container_table_body.find_all('tr')
            table_text = {}
            for row in rows:
                cols = row.find_all('td')
                # Store percentage as a float for now so we can sort the rows later by stripping the percent sign and
                # any whitespace with regex
                try:
                    table_text[cols[1].text.strip()] = float(cols[4].text.strip().rstrip(u'% \n\t\r\xa0'))
                except Exception as e:
                    await message.channel.send(best_container.text + ' has no drop table. If this was not the item you'
                                                                     ' were looking for enter a more specific name')
                    return

            sorted_text = sorted((key, value) for (value, key) in table_text.items())

            table_string = ''
            for text in sorted_text:
                table_string += str(text[1]).ljust(30) + '\t' + str(text[0]).rjust(6) + '%\n'
            await message.channel.send('Displaying drop table for **' + best_container.text + '**:\n')
            # Discord's max message length is 2000. If our message exceeds that, split it up into different messages
            if len(table_string) > 2000:
                # Split the message every 1900 character, preserving formatting
                messages = textwrap.wrap(table_string, 1800, break_long_words=False, replace_whitespace=False)
                # Once the message has been split into a list, iterate through and post it as code to make it look
                # halfway decent
                for msg in messages:
                    await message.channel.send('```' + msg + '```')
                await message.channel.send('Discord is not hot when it comes to string formatting! Sauce them'
                                           ' an angry letter if u think this looks like hot dog')
            else:
                await message.channel.send('```' + table_string + '```')

    # Posts a random picture from a given folder
    elif message.content.lower().startswith('!campic'):
        img_path = 'C:/Users/Stefon/PycharmProjects/CamBot/Cam/'
        pics = []
        # Get the filenames of all images in the directory
        for fileName in os.listdir(img_path):
            pics.append(fileName)

        # Select a random filename from the list and upload the corresponding image
        rand_pic = random.choice(pics)
        print(img_path + rand_pic)
        file = discord.File(img_path + rand_pic, filename=rand_pic)
        await message.channel.send(file=file)


    # Output all loot sources that give a certain item
    elif message.content.lower().startswith('!lootfrom'):
        args = message.content.lower().split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display all loot sources that drop a certain item, along '
                                       'with their respective percentages. Use **!lootfrom [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            best_item = get_item(' '.join(args[1:]))
            item_url = 'https://www.rustlabs.com' + best_item['href'] + '#tab=loot;sort=3,1,0'
            container_html = get_html(item_url)
            # Hack for items that have stats(damage/protection values, etc.)
            item_table = container_html.find('table', {"class": "table w100 olive sorting"})
            item_table_body = item_table.find('tbody')
            # For each row in the tbody, insert columns 1 and 4 as an entry into an output string. I wanted to
            # use an embed for its nice columns(which discord doesn't support as of yet) but a lot of the time there
            # were more than 25 entries which is discord's max for an embed
            rows = item_table_body.find_all('tr')
            table_text = {}
            for row in rows:
                cols = row.find_all('td')
                # Store percentage as a float for now so we can sort the rows later using regex to stip the percent sign
                # and any whitespace
                try:
                    table_text[cols[0].text.strip()] = float(cols[3].text.strip().rstrip(u'% \n\t\r\xa0'))
                except Exception as e:
                    await message.channel.send(best_item.text + ' has no loot source. If this was not the item you '
                                                                'were looking enter a more specific name')
                    return
            # Once we get all of the drop data, sort it based on drop percentage
            sorted_text = sorted((key, value) for (value, key) in table_text.items())
            table_string = ''
            for text in sorted_text:
                table_string += str(text[1]).ljust(30) + '\t' + str(text[0]).rjust(6) + '%\n'
            await message.channel.send('Displaying drop percentages for **' + best_item.text + '**:\n')
            # Discord's max message length is 2000. If our message exceeds that, split it up into different messages
            if len(table_string) > 2000:
                # Split the message every 1900 character, preserving formatting
                messages = textwrap.wrap(table_string, 1800, break_long_words=False, replace_whitespace=False)
                # Once the message has been split into a list, iterate through and post it as code to make it look
                # halfway decent
                for msg in messages:
                    await message.channel.send('```' + msg + '```')
                await message.channel.send('Discord is not hot when it comes to string formatting! Sauce them'
                                           ' an angry letter if u think this looks like hot dog')
            else:
                await message.channel.send('```' + table_string + '```')

    # Output general smelting info about a certain item.
    elif message.content.lower().startswith('!smelting'):
        args = message.content.lower().split()
        # Print out a command description if the user doesn't enter a second argument
        if len(args) == 1:
            embed = discord.Embed()
            embed.add_field(name="Barbeque", value="\n\u200b", inline=False)
            embed.add_field(name="Camp Fire", value="\n\u200b", inline=False)
            embed.add_field(name="Furnace", value="\n\u200b", inline=False)
            embed.add_field(name="Large Furnace", value="\n\u200b", inline=False)
            embed.add_field(name="Small Oil Refinery", value="\n\u200b", inline=False)
            await message.channel.send('This command will display smelting data for a given item with '
                                       '**!smelting [itemName]** \nThe following items are currently supported:',
                                       embed=embed)

        # If the user enters an item, look for it in the current list of supported items
        else:
            # Hardcode all of the supported smelting items into a BS4 tag list and get the best match. This seems
            # much more efficient than scanning all items as I would have to compare them to these 5 values anyways
            # and the former option would be way slower than this. Additionally, a smelting item hasn't been added to
            # rust in years so it seems safe to hardcode them
            item_name = ' '.join(args[1:])

            # Create a tag for each supported item and pass them off to get_best_match as a list of tags
            soup = BeautifulSoup(features="lxml")
            smelt_links = []
            temp_link1 = soup.new_tag('a', href='https://rustlabs.com/item/barbeque#tab=smelting')
            temp_link1.string = 'Barbeque'
            smelt_links.append(temp_link1)
            temp_link2 = soup.new_tag('a', href='https://rustlabs.com/item/camp-fire#tab=smelting')
            temp_link2.string = 'Camp Fire'
            smelt_links.append(temp_link2)
            temp_link3 = soup.new_tag('a', href='https://rustlabs.com/item/furnace#tab=smelting')
            temp_link3.string = 'Furnace'
            smelt_links.append(temp_link3)
            temp_link4 = soup.new_tag('a', href='https://rustlabs.com/item/large-furnace#tab=smelting')
            temp_link4.string = 'Large Furnace'
            smelt_links.append(temp_link4)
            temp_link5 = soup.new_tag('a', href='https://rustlabs.com/item/small-oil-refinery#tab=smelting')
            temp_link5.string = 'Small Oil Refinery'
            smelt_links.append(temp_link5)

            best_smelt = get_best_match(smelt_links, item_name)
            best_smelt_html = get_html(best_smelt['href'])
            best_smelt_table = best_smelt_html.find('div', {"data-name": "smelting"}).find('table', {
                "class": "table w100 olive"}).find('tbody')
            rows = best_smelt_table.find_all('tr')
            table_text = 'Displaying smelting stats for **' + best_smelt.text + '**```'
            for row in rows:
                cols = row.find_all('a')
                # If there are only 2 entries in the row, we are at the end of the table
                if len(cols) == 2:
                    pass
                else:
                    # Try to parse the smelting data, if we are unable to then the item has no smelting data
                    try:
                        table_text += 'It takes ' + cols[1].find('span').text[1:] + ' wood to smelt 1 ' + \
                                      cols[0].find('img')['alt'] + '\n'
                    except Exception as e:
                        await message.channel.send('There is no smelting data for ' +
                                                   best_smelt.text + '. If this is not the item you searched for, '
                                                                     'please be more specific')
            table_text += '```'

            await message.channel.send(table_text)

    # Displays all stats pertaining to the item the user searches for
    elif message.content.lower().startswith('!stats'):
        args = message.content.lower().split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display all stats corresponding to a given item. Use **!stats'
                                       ' [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            best_item = get_item(' '.join(args[1:]))
            item_url = 'https://www.rustlabs.com' + best_item['href']
            # Get the stats table from the corresponding item's info page
            stats_html = get_html(item_url)
            stats_table = stats_html.find('table', {"class": "info-table"})
            # If the html returned is null, then there are no stats for the item
            if stats_table is None:
                await message.channel.send('There are no stats for ' + best_item.text)
            # If the item has stats, then output all rows into an embed to display to the user
            else:
                rows = stats_table.find_all('tr')
                embed = discord.Embed()
                for row in rows:
                    data = row.find_all('td')
                    embed.add_field(name=data[0].text, value=data[1].text, inline=True)
                await message.channel.send('Displaying item stats for **' + best_item.text + '**:', embed=embed)

    elif message.content.lower().startswith('!repair'):
        args = message.content.lower().split()
        # Print out a command description if the user doesn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will display the repair cost for a given item. Use **!repair'
                                       ' [itemName]**')
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            best_item = get_item(' '.join(args[1:]))
            item_url = 'https://www.rustlabs.com' + best_item['href'] + '#tab=repair'
            # Get the stats table from the corresponding item's info page
            repair_html = get_html(item_url)
            # Get the repair data and output it as an embed. If there is an error when getting the data, then
            # there is no repair data for the given item
            try:
                repair_table = repair_html.find('div', {"data-name": "repair"})
                repair_table_body = repair_table.find('tbody')
                # Get the materials, condition loss, and bool pertaining to if a blueprint is required to repair for
                # the item
                row = repair_table_body.find('tr')
                cols = row.find_all('td')
                embed = discord.Embed()
                materials = cols[2].find_all('img')
                for material in materials:
                    material_name = material['alt']
                    quantity = material.find_next_sibling().text[1:]
                    # If the quantity is empty, then there is only 1 of that material required
                    if quantity == '':
                        quantity = 1
                    embed.add_field(name=material_name, value=quantity, inline=False)
                embed.add_field(name="Condition Loss", value=cols[3].text, inline=False)
                embed.add_field(name="Blueprint required?", value=cols[4].text, inline=False)
            except Exception as e:
                await message.channel.send(best_item.text + ' has no repair data. Use **!repair [itemName]**')
                return
            # Output the item's repair data as an embed
            await message.channel.send('Displaying repair cost for **' + best_item.text + '**:', embed=embed)

    # Outputs the most efficient furnace ratios for a specific furnace and ore type
    elif message.content.lower().startswith('!furnaceratios'):
        args = message.content.lower().split()
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
    elif message.content.lower().startswith('!sulfur'):
        args = message.content.lower().split()
        # If len(args) is 1, the user didn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will output the amount of explosives you can sauce with a given '
                                       'sulfur amount. Use **!sulfur [sulfuramount]**')
        elif len(args) > 2:
            await message.channel.send('Too many arguments, please enter **!suflur [sulfuramount]**.'
                                       ' If you have gunpower, simply multiply it by 2 to get the amount of sulfur')
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
                await message.channel.send(sulf_calc(num_sulf))

    # Displays the current list of rust items for sale, along with their prices
    elif message.content.lower().startswith('!rustitems'):
        items, total_item_price = get_rust_items('https://store.steampowered.com/itemstore/252490/browse/?filter=All')
        total_item_price = '$' + str("{:.2f}".format(total_item_price))
        # If the dictionary is empty, then the item store is having an error or is updating
        if not bool(items):
            await message.channel.send('Rust item store is not hot!!!')
        # If we have entries, format and display them
        else:
            embed = discord.Embed()
            # Format the strings for display in an embed
            for item in items:
                item_text = '**' + item + '**'
                embed.add_field(name='**' + item_text + '**', value=items[item], inline=False)
            embed.add_field(name='**Total Price:** ', value=total_item_price, inline=False)
            item_str = 'Item store: ' + 'https://store.steampowered.com/itemstore/252490/browse/?filter=All' + '\n\n'
            await message.channel.send(item_str, embed=embed)


    # Gets the recipe for a certain item
    elif message.content.lower().startswith('!craftcalc'):
        craft_name = []
        args = message.content.lower().split()
        # If len(args) is 1, the user didn't enter an item name
        if len(args) == 1:
            await message.channel.send('This command will output the recipe of any item in rust that has a recipe.\n'
                                       'Use **!craftcalc [itemname] [quantity]**')
        else:
            for i in args:
                # Omit the !craftcalc command and the item number from the item name
                if i == args[0] or i == args[-1]:
                    pass
                else:
                    craft_name.append(i)
            # Try to convert the last word in the command to an int to test if the user entered an amount
            try:
                # If the user entered an amount, check if it is a valid amount
                args[-1] = int(args[-1])
                if args[-1] <= 0:
                    await message.channel.send('Please enter a valid number')
                else:
                    # If the user entered a valid amount, call craft_calc with the amount
                    craftnum = args[-1]
                    await message.channel.send(craft_calc(' '.join(craft_name), craftnum))
            # If the user didn't enter an amount, add the last word to the item name and call craft_calc with 1 as
            # the amount
            except Exception as e:
                if not craft_name:
                    craft_name.append(i)
                await message.channel.send(craft_calc(' '.join(craft_name), 1))

    # Tweet a message using tweepy
    elif message.content.lower().startswith('!tweet'):
        msg = '@yvngalec @AidanT5 TEST TWEET YES'
        pic = 'C:/Users/Stefon/PycharmProjects/CamBot/delete.jpg'
        await message.channel.send(tweet(msg, pic))

    # Get status of all servers the bot depends on with get_status
    elif message.content.lower().startswith('!status'):
        await message.channel.send(get_status())


client.loop.create_task(check())
client.run(keys[0])
