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
    itemArr = item.split()
    itemURL = "-".join(itemArr)
    capitalized_parts = [i.capitalize() for i in itemArr]
    itemalt = " ".join(capitalized_parts) + ' Blueprint'
    url = 'https://rustlabs.com/item/' + itemURL + '#tab=craft'
    try:
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                items = html.find('img', alt = itemalt).parent.find_next_sibling('td').find_next_sibling('td').select('a')
                tempstr = 'Crafting cost for **' + item.title() + '**:\n'
                for component in items:
                    tempstr += '\t' + component.img['alt'] + ' ' + component.text + '\n'
                return(tempstr)


            else:
                return 'Item recipe not found'


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

    #TODO list recipes for requested items / sulfur amount
    elif message.content.lower().startswith('!serverpop'):
        await message.channel.send('Rustafied Trio currently has ' + P() + ' players online')

    elif message.content.lower().startswith('!craftcalc'):
        first, _, rest = message.content.lower().partition(" ")
        rest or first
        try:
            pnum = rest.rsplit(' ', 1)[1]
            if(pnum.isnumeric()):
                item = rest.rsplit(' ', 1)[0]
                await message.channel.send(craftCalc(item, pnum))
            else:
                await message.channel.send(craftCalc(rest, 1))
        except:
            await message.channel.send(craftCalc(rest, 1))
        #await message.channel.send(craftCalc(cmd[1]))

    #DONE
    elif message.content.lower().startswith('!status'):
        if(getStatus()):
            await message.channel.send('All servs r hot n ready like little C\'s')
        else:
            await message.channel.send('Servs are NOT hot!!!')



client.run('Njg0MDU4MzU5Njg2ODg5NDgz.XmJmdA.c2dE6my-hyZIVpPGkJlJjqqUInY')
