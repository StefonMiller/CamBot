import re
import discord
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import Error
import tweepy
from datetime import datetime

with open('C:/Users/Stefon/PycharmProjects/CamBot/keys.txt') as f:
    keys = f.read().splitlines()

with open('C:/Users/Stefon/PycharmProjects/CamBot/serverinfo.txt') as f:
    server_info = f.read().splitlines()

client = discord.Client()
try:
    c = mysql.connector.connect(host=server_info[0], database=server_info[1],
                                user=server_info[2], password=server_info[3])
    cursor = c.cursor()
    print('Connected to server')
except mysql.connector.Error as e:
    print('Failed to connect to server'.format(e))


def list_commands():
    return ('Here is a list of commands:\n'
            '\t**!craftcalc** outputs the recipe of a certain item\n'
            '\t**!status** gives you the current status of Cambot\'s dependent servers\n'
            '\t**!serverpop** gives the current pop for our frequented servers. Use !serverpop [servername] to get '
            'information about another server\n')


def server_pop(url):
    try:
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                pop = html.find('dt', string='Player count').find_next_sibling('dd')
                return pop.text

            else:
                return 'Server not found'

    except RequestException:
        return 'Connection to Battlemetrics failed'


def get_status():
    import requests
    p = requests.head('https://www.battlemetrics.com/')
    return p.status_code == 200


def craft_calc(item_name, num_crafts):
    cost = ""
    sql_select_query = """SELECT * FROM craft_recipe WHERE fk_item_name = %s"""
    cursor.execute(sql_select_query, (item_name,))
    record = cursor.fetchall()
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


def get_best_match(servers, search_name):
    for i in servers:
        name = i.find('a').get('title')
        best = True
        for j in search_name:
            if j.lower() in name.lower():
                pass
            else:
                best = False
        if best:
            return i
    return ''


def tweet(msg, pic):
    auth = tweepy.OAuthHandler(keys[1], keys[2])
    auth.set_access_token(keys[3], keys[4])

    api = tweepy.API(auth)

    try:
        api.verify_credentials()
        print('Authentication OK')
    except:
        print('Error during authentication')
    if pic is None:
        api.update_status(msg)
    else:
        media = api.media_upload(pic)
        tweet = msg
        post_result = api.update_status(status=tweet, media_ids=[media.media_id])


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # TODO Finish command list
    if message.content.lower().startswith('!cambot help'):
        await message.channel.send(list_commands())

    # DONE
    elif message.content.lower().startswith('!serverpop'):
        args = message.content.lower().split()
        if len(args) == 1:
            await message.channel.send('Rustafied Trio currently has ' + server_pop(
                'https://www.battlemetrics.com/servers/rust/2634280') + ' players online\n'
                                                                        'Bloo Lagoon currently has ' + server_pop(
                'https://www.battlemetrics.com/servers/rust/3461363') + ' players online')
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
            url = 'https://battlemetrics.com/servers/rust?q=' + serv_name + '&sort=rank'
            print(url)
            try:
                with closing(get(url, stream=True)) as resp:
                    content_type = resp.headers['Content-Type'].lower()
                    if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                        html = BeautifulSoup(resp.content, 'html.parser')
                        server_table = html.find('table', {"class": "css-1yjs8zt"})
                        entries = server_table.find('tbody').contents
                        servers = []
                        for i in entries:
                            if i.find('a'):
                                servers.append(i)
                        best_match = get_best_match(servers, serv_name.split())
                        if best_match == '':
                            print('Server not found')
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

    elif message.content.lower().startswith('!craftcalc'):
        craftname = ""
        args = message.content.lower().split()
        if len(args) == 1:
            await message.channel.send('Please enter an item name')
        else:
            for i in args:
                if i == args[0] or i == args[-1]:
                    pass
                else:
                    if craftname == "":
                        craftname = i.capitalize()
                    else:
                        craftname = craftname + " " + i.capitalize()
            try:
                args[-1] = int(args[-1])
                if args[-1] <= 0:
                    print('Please enter a valid number')
                else:
                    craftnum = args[-1]
                    await message.channel.send(craft_calc(craftname, craftnum))
            except Exception as e:
                if craftname == "":
                    craftname = i.capitalize()
                else:
                    craftname = craftname + " " + i.capitalize()
                await message.channel.send(craft_calc(craftname, 1))

    elif message.content.lower().startswith('!tweet'):
        msg = '@yvngalec @AidanT5 TEST TWEET YES'
        pic = 'C:/Users/Stefon/PycharmProjects/CamBot/delete.jpg'
        tweet(msg, pic)
        await message.channel.send('New tweet created at ' + datetime.now().strftime("%m-%d-%Y %H:%M:%S") + ' EST')

    # DONE
    elif message.content.lower().startswith('!status'):
        if get_status():
            await message.channel.send('All servs r hot n ready like little C\'s')
        else:
            await message.channel.send('Servs are NOT hot!!!')


client.run(keys[0])
