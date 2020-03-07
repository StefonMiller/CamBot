import re
import discord
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup

client = discord.Client()

def listCommands():
    return ('Here is a list of commands:\n'\
           '\t**!craftcalc** outputs the amount of sulfur required for explosives or how much of a '
            'certain explosive you can make with however much sulfur\n'
            '\t**!status** gives you the current status of Cambot\'s dependent servers\n'
            '\t**!serverpop gives the current pop for Rustafied Trio')

def serverPop():
    url = 'https://www.battlemetrics.com/servers/rust/2634280'
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

def craftCalc(item, numItem):
    print(item)
    itemArr = item.split()
    print(itemArr)
    itemURL = "-".join(itemArr)
    capitalized_parts = [i.title() for i in itemArr]
    itemAlt = " ".join(capitalized_parts) + ' Blueprint'
    print(itemURL)
    print(itemAlt)
    url = 'https://rustlabs.com/item/' + itemURL + '#tab=craft'
    try:
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                #try:
                items = html.find('img', alt = itemAlt).parent.find_next_sibling('td').find_next_sibling('td').select('a')
                tempstr = 'Crafting cost for **' + item.title() + '**:\n'
                for component in items:
                    try:
                        num = re.search(r'\d+', component.text).group()
                    except Exception as e1:
                        num = 1
                    tempstr += '\t' + component.img['alt'] + ' x' + (str(int(num) * int(numItem))) + '\n'
                return(tempstr)
                #except Exception as e:
                    #print(e)
                    #return 'Item not found'


            else:
                return 'Item not found'


    except RequestException as e:
        return 'Connection to RustLabs failed'



def getStatus():
    import requests
    r = requests.head('https://rustlabs.com/')
    p = requests.head('https://www.battlemetrics.com/')
    return r.status_code == 200 and p.status_code == 200

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    #TODO Finish command list
    if message.content.lower().startswith('!cambot help'):
        await message.channel.send(listCommands())

    #DONE
    elif message.content.lower().startswith('!serverpop'):
        await message.channel.send('Rustafied Trio currently has ' + P() + ' players online')

    #TODO Add aliases, fix all caps words, add multiplier for numCrafts
    elif message.content.lower().startswith('!craftcalc'):
        first, _, rest = message.content.lower().partition(" ")
        rest or first
        try:
            pnum = rest.rsplit(' ', 1)[1]
        except IndexError as e:
            print(e)
            await message.channel.send(craftCalc(rest, 1))

        if(pnum.isnumeric()):
            item = rest.rsplit(' ', 1)[0]
            print(pnum)
            print(item)
            await message.channel.send(craftCalc(item, pnum))
        else:
            await message.channel.send(craftCalc(rest, 1))


    #DONE
    elif message.content.lower().startswith('!status'):
        if(getStatus()):
            await message.channel.send('All servs r hot n ready like little C\'s')
        else:
            await message.channel.send('Servs are NOT hot!!!')



client.run('Njg0MDU4MzU5Njg2ODg5NDgz.XmLxFA.FkiSiSH14Unaj6ZRE7usAcJvukc')
