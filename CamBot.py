import re
import time
import urllib

import discord
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
import mysql.connector
import tweepy
from datetime import datetime
import xml.etree.ElementTree as ET
import csv
import requests

# Get API keys from keys text file
with open('C:/Users/Stefon/PycharmProjects/CamBot/keys.txt') as f:
    keys = f.read().splitlines()
# Get SQL connection info from serverinfo text file
with open('C:/Users/Stefon/PycharmProjects/CamBot/serverinfo.txt') as f:
    server_info = f.read().splitlines()
# Create client object for discord integration
client = discord.Client()
# Attempt connection to SQL server and create the cursor object for executing queries
try:
    c = mysql.connector.connect(host=server_info[0], database=server_info[1],
                                user=server_info[2], password=server_info[3])
    cursor = c.cursor()
    print('Connected to server')
except mysql.connector.Error as e:
    print('Failed to connect to server'.format(e))


# List all working commands for the discord bot
def list_commands():
    return ('Here is a list of commands:\n'
            '\t**!craftcalc** outputs the recipe of a certain item\n'
            '\t**!status** gives you the current status of Cambot\'s dependent servers\n'
            '\t**!serverpop** gives the current pop for our frequented servers. Use !serverpop [servername] to get '
            'information about another server\n')


# Returns the player count of a certain server URL on Battlemetrics.com
# @Param url: - url of the server we want the player count of
# @Return: - number of players on the server
def server_pop(url):
    try:
        # Try to connect to the server
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            # If we are able to connect, find the dt containing the player cound and return the text
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                pop = html.find('dt', string='Player count').find_next_sibling('dd')
                return pop.text

            else:
                return 'Server not found'

    except RequestException:
        return 'Connection to Battlemetrics failed'


# Gets the status of all servers the CamBot is dependent on
# @Return: whether or not we were able to successfully connect to all servers
def get_status():
    # Attempt connection to each dependent server and if the status is not 200, return false
    import requests
    servers = [requests.head('https://www.battlemetrics.com/'), requests.head('https://rust.facepunch.com/blog/')]

    for server in servers:
        if server.status_code != 200:
            return 'Servs r NOT hot!!!'
    return 'All servs r hot n ready like little C\'s'


# Returns the crafting recipe for a certain item in the rustitem database
# @Param item_name: name of the item to get from the database
# @Param num_crafts: number of times to craft said item
# @Return: Total crafting cost for the requested item * num_crafts
def craft_calc(item_name, num_crafts):
    # Select the recipe from the database with the corresponding item name
    cost = ""
    sql_select_query = """SELECT * FROM craft_recipe WHERE fk_item_name = %s"""
    cursor.execute(sql_select_query, (item_name,))
    record = cursor.fetchall()
    # Multiply the number of crafts times the cost in the database for each recipe entry
    for row in record:
        num_cost = int(num_crafts) * row[3]
        if row[1] is None:
            cost = cost + ' **' + row[2] + '**:\t' + str(f"{num_cost:,}") + '\n'
        elif row[2] is None:
            cost = cost + ' **' + row[1] + '**\t' + str(f"{num_cost:,}") + '\n'
    if not record:
        return 'Item not found in database'
    else:
        return 'Crafting cost for ' + str(num_crafts) + ' ' + item_name + ':\n' + cost


# Returns the first server that contains each search term. Since the servers are already sorted by rank, this will
# return the best server that matches each search term
# @Param servers: List of servers
# @Param search_name: List of search terms
# @Return: First server from the servers list that matches each item in search_name
def get_best_match(servers, search_name):
    # Iterate through each server and test if they contain each search term
    for i in servers:
        name = i.find('a').get('title')
        best = True
        # If one search term is not found in the server, it is not the best match
        for j in search_name:
            if j.lower() in name.lower():
                pass
            else:
                best = False
        # Return the first server matching each term, otherwise return an empty string
        if best:
            return i
    return ''


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
def get_devblog(url, kw1, kw2):
    with urllib.request.urlopen(url) as u:
        xml = BeautifulSoup(u, 'xml')
        titles = xml.find_all('title')
        for title in titles:
            if title.find(text=re.compile(kw1)) and not title.find(text=re.compile(kw2)):
                link = title.find_next_sibling('a10:link')
                desc = title.find_next_sibling('description')
                description = desc.text.split("<br/>", 1)[1]
                return str(title.text), link['href'], description
        return 'No Devblog found'


def get_news(url):
    try:
        # Try to connect to the server
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            # If we are able to connect, find the dt containing the player cound and return the text
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                title_element = html.find('h1', {"class": "entry-title"})
                desc_element = html.find('p', {"style": "white-space:pre-wrap;"})
                return title_element.text, desc_element.text
            else:
                return 'Rustafied update page not found'

    except RequestException:
        return 'Connection to Rustafied failed'


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    # Ignore messages from the bot to avoid infinite looping
    if message.author == client.user:
        return

    # TODO Finish command list
    # Display all commands
    if message.content.lower().startswith('!cambot help'):
        await message.channel.send(list_commands())

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
                'https://www.battlemetrics.com/servers/rust/3461363') + ' players online')
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
            url = 'https://battlemetrics.com/servers/rust?q=' + serv_name + '&sort=rank'
            try:
                with closing(get(url, stream=True)) as resp:
                    content_type = resp.headers['Content-Type'].lower()
                    if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                        html = BeautifulSoup(resp.content, 'html.parser')
                        # Find the table containing the search results
                        server_table = html.find('table', {"class": "css-1yjs8zt"})
                        # Get all children of the table
                        entries = server_table.find('tbody').contents
                        servers = []
                        # Omit any results not containing a link
                        # This mitigates the style child of the tbody
                        for i in entries:
                            if i.find('a'):
                                servers.append(i)
                        # Find the best match given the new list of servers and all search terms
                        best_match = get_best_match(servers, serv_name.split())
                        # If get_best_match returns an empty string, there was no matching server
                        if best_match == '':
                            print('Server not found')
                        # If we did find a server, get the link from the html element and get its pop via server_pop
                        else:
                            link = best_match.find('a').get('href')
                            serv_name = best_match.find('a').get('title')
                            url = 'https://battlemetrics.com' + link
                            await message.channel.send(
                                serv_name + ' currently has ' + server_pop(url) + ' players online')
                    else:
                        print('Server not found')

            except RequestException as e:
                print('Connection to Battlemetrics failed' + e)

    elif message.content.lower().startswith('!rustnews'):
        title, desc = get_news('https://rustafied.com')
        embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
        await message.channel.send('This will be used in the future to make a discord post whenever Rustafied updates '
                                   'with news', embed=embed)

    # Outputs a link to of the newest rust devblog. I am using an xml parser to scrape the rss feed as the
    # website was JS rendered and I could not get selerium/pyqt/anything to return all of the html that I needed
    elif message.content.lower().startswith('!devblog'):
        title, url, desc = get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')
        embed = discord.Embed(title=title, url=url, description=desc)
        await message.channel.send('Newest Rust Devblog:', embed=embed)


    # Gets the recipe for a certain item
    elif message.content.lower().startswith('!craftcalc'):
        craft_name = ""
        args = message.content.lower().split()
        # If len(args) is 1, the user didn't enter an item name
        if len(args) == 1:
            await message.channel.send('Please enter an item name')
        else:
            for i in args:
                # Omit the !craftcalc command and the item number from the item name
                if i == args[0] or i == args[-1]:
                    pass
                else:
                    # Re-integrate the list of words into a single string for the item name
                    # Add a space between each word, but if the string is empty just add the word
                    if craft_name == "":
                        craft_name = i.capitalize()
                    else:
                        craft_name = craft_name + " " + i.capitalize()
            # Try to convert the last word in the command to an int to test if the user entered an amount
            try:
                # If the user entered an amount, check if it is a valid amount
                args[-1] = int(args[-1])
                if args[-1] <= 0:
                    print('Please enter a valid number')
                else:
                    # If the user entered a valid amount, call craft_calc with the amount
                    craftnum = args[-1]
                    await message.channel.send(craft_calc(craft_name, craftnum))
            # If the user didn't enter an amount, add the last word to the item name and call craft_calc with 1 as
            # the amount
            except Exception as e:
                if craft_name == "":
                    craft_name = i.capitalize()
                else:
                    craft_name = craft_name + " " + i.capitalize()
                await message.channel.send(craft_calc(craft_name, 1))

    # Tweet a message using tweepy
    elif message.content.lower().startswith('!tweet'):
        msg = '@yvngalec @AidanT5 TEST TWEET YES'
        pic = 'C:/Users/Stefon/PycharmProjects/CamBot/delete.jpg'
        await message.channel.send(tweet(msg, pic))

    # Get status of all servers the bot depends on with get_status
    elif message.content.lower().startswith('!status'):
        await message.channel.send(get_status())


client.run(keys[0])
