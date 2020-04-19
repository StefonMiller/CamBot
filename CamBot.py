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

client = discord.Client()
try:
    c = mysql.connector.connect(host='rustitems.cfo3xmszwucs.us-east-2.rds.amazonaws.com', database='rustitems',
                                user='root', password='Stefonmiller1')
    cursor = c.cursor()
    print('Connected to server')
except mysql.connector.Error as e:
    print('Failed to connect to server'.format(e))


def listCommands():
    return ('Here is a list of commands:\n'
            '\t**!craftcalc** outputs the recipe of a certain item\n'
            '\t**!status** gives you the current status of Cambot\'s dependent servers\n'
            '\t**!serverpop gives the current pop for Rustafied Trio')


def serverPop(url):
    try:
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                pop = html.find('dt', string='Player count').find_next_sibling('dd')
                return pop.text

            else:
                return 'Server not found'


    except RequestException as e:
        return 'Connection to Battlemetrics failed'


def getStatus():
    import requests
    p = requests.head('https://www.battlemetrics.com/')
    return p.status_code == 200


def craftCalc(itemName, numCrafts):
    cost = ""
    sql_select_query = """SELECT * FROM craft_recipe WHERE fk_item_name = %s"""
    cursor.execute(sql_select_query, (itemName,))
    record = cursor.fetchall()
    for row in record:
        numcost = int(numCrafts) * row[3]
        if row[1] is None:
            cost = cost + " **" + row[2] + "**:\t" + str(f"{numcost:,}") + "\n"
        elif row[2] is None:
            cost = cost + " **" + row[1] + "**\t" + str(f"{numcost:,}") + "\n"
    return cost

def tweet(msg):
    auth = tweepy.OAuthHandler(keys[1], keys[2])
    auth.set_access_token(keys[3], keys[4])

    api = tweepy.API(auth)

    try:
        api.verify_credentials()
        print("Authentication OK")
    except:
        print("Error during authentication")

    api.update_status(msg)

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # TODO Finish command list
    if message.content.lower().startswith('!cambot help'):
        await message.channel.send(listCommands())

    # DONE
    elif message.content.lower().startswith('!serverpop'):
        await message.channel.send('Rustafied Trio currently has ' + serverPop(
            'https://www.battlemetrics.com/servers/rust/2634280') + ' players online\n'
                                                                    'Bloo Lagoon currently has ' + serverPop(
            'https://www.battlemetrics.com/servers/rust/3461363') + ' players online')

    elif message.content.lower().startswith('!craftcalc'):
        craftname = ""
        args = message.content.lower().split()
        if len(args) == 1:
            await message.channel.send("Please enter an item name")
        else:
            for i in args:
                if i == args[-1]:
                    craftnum = i
                elif i == args[0]:
                    pass
                else:
                    if craftname == "":
                        craftname = i.capitalize()
                    else:
                        craftname = craftname + " " + i.capitalize()
            try:
                int(args[-1])
                await message.channel.send(
                    "Crafting cost for " + craftnum + " " + craftname + ":\n" + craftCalc(craftname, craftnum))
            except Exception as e:
                if craftname == "":
                    craftname = i.capitalize()
                else:
                    craftname = craftname + " " + i.capitalize()
                await message.channel.send("Crafting cost for 1 " + craftname + ":\n" + craftCalc(craftname, 1))

    elif message.content.lower().startswith('!tweet'):
        msg = 'HELLO IT IS ME FIRST WORDS ON HERE'
        tweet(msg)
        await message.channel.send("New tweet created at " + datetime.now().strftime("%m-%d-%Y %H:%M:%S") + "EST")

    # DONE
    elif message.content.lower().startswith('!status'):
        if getStatus():
            await message.channel.send('All servs r hot n ready like little C\'s')
        else:
            await message.channel.send('Servs are NOT hot!!!')


client.run(keys[0])
