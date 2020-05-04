import re
import textwrap
import urllib
import discord
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
import tweepy
from datetime import datetime
from fuzzywuzzy import fuzz

# Get API keys from keys text file
with open('C:/Users/Stefon/PycharmProjects/CamBot/keys.txt') as f:
    keys = f.read().splitlines()
# Create client object for discord integration
client = discord.Client()


# List all working commands for the discord bot
def list_commands():
    return ('Here is a list of commands:\n'
            '\t**!craftcalc** outputs the recipe of a certain item\n'
            '\t**!status** gives you the current status of Cambot\'s dependent servers\n'
            '\t**!serverpop** gives the current pop for our frequented servers. Use !serverpop [servername] to get '
            'information about another server\n'
            '\t**!devblog** posts a link to the newest devblog with a short summary\n'
            '\t**!rustnews** posts a link to the latest news on the new Rust update\n'
            '\t**!rustitems** displays all items on the rust store along with prices\n')


# Returns the player count of a certain server URL on Battlemetrics.com
# @Param serv_url: - url of the server we want the player count of
# @Return: - number of players on the server
def server_pop(serv_url):
    serv_html = get_html(serv_url)
    pop = serv_html.find('dt', string='Player count').find_next_sibling('dd')
    return pop.text


# Gets the status of all servers the CamBot is dependent on
# @Return: whether or not we were able to successfully connect to all servers
def get_status():
    # Attempt connection to each dependent server and if the status is not 200, return false
    import requests
    servers = [requests.head('https://www.battlemetrics.com/'), requests.head('https://rust.facepunch.com/blog/')
        , requests.head('https://www.rustlabs.com/'), requests.head('https://rustafied.com/')]

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
    item = get_best_match(item_list, search_term, 1)
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
def get_best_match(i_list, term, scorer=1):
    # This could be done with fuzzywuzzy's process.extractOne module, but I could not get it to work with a different
    # scorer than WRatio.
    best_item_match = None
    best_item_match_num = 0
    for i in i_list:
        # Get an average of multiple fuzzywuzzy scorers to get a better match
        r = fuzz.ratio(term, i.text)
        s = fuzz.token_set_ratio(term, i.text)
        srt = fuzz.token_sort_ratio(term, i.text)
        p = fuzz.partial_ratio(term, i.text)
        temp_ratio = (r + s + srt + p) / 4

        if temp_ratio > best_item_match_num:
            best_item_match = i
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


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    # Ignore messages from the bot to avoid infinite looping
    if message.author == client.user:
        return
    # Dont bother processing a message if it isn't a command
    if not message.content.lower().startswith('!'):
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
            best_match = get_best_match(servers, serv_name, 2)
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
    # TODO fix item searching algorithm
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
            best_container = get_best_match(container_links, container_name, 1)
            container_url = 'https://www.rustlabs.com' + best_container['href'] + '#tab=content;sort=3,1,0'
            container_html = get_html(container_url)
            # Hack for loot tables that have HP values(scientists, etc)
            container_table = container_html.find('table', {"class": "table w100 olive sorting"})
            container_table_body = container_table.find('tbody')
            # For each row in the tbody, insert columns 1 and 4 as an entry into an output string. I wanted to
            # use an embed for its nice columns(which discord doesn't support as of yet) but a lot of the time there
            # were more than 25 entires which is discord's max for an embed
            rows = container_table_body.find_all('tr')
            table_text = {}
            for row in rows:
                cols = row.find_all('td')
                # Store percentage as int for now so we can sort the rows later
                table_text[cols[1].text.strip()] = float(cols[4].text.strip().rstrip(u'% \n\t\r\xa0'))

            sorted_text = sorted((key, value) for(value, key) in table_text.items())

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



    # Output all loot sources that give a certain item
    elif message.content.lower().startswith('!lootfrom'):
        args = message.content.lower().split()
        # Print out a table list if the user doesn't enter a specific one
        if len(args) == 1:
            await message.channel.send('This command will display all loot sources that drop a certain item, along '
                                       'with their respective percentages. Use **!lootfrom [itemName]**')
        # If the user enters an item, search for it
        else:
            pass

    # Outputs how many explosives you can craft with x sulfur
    elif message.content.lower().startswith('!sulfur'):
        args = message.content.lower().split()
        # If len(args) is 1, the user didn't enter an item name
        if len(args) == 1:
            await message.channel.send('To use !sulfur, enter the amount of sulfur you have. I will then spit oot'
                                       ' how many of each explosive you can SAUCE')
        elif len(args) > 2:
            await message.channel.send('Too many arguments, please enter !suflur [sulfur amount]. If you have gunpower,'
                                       ' simply multiply it by 2 to get the amount of sulfur')
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
        store_url = 'https://store.steampowered.com/itemstore/252490/browse/?filter=All'
        items, total_item_price = get_rust_items(store_url)
        total_item_price = '$' + str("{:.2f}".format(total_item_price))
        # If the dictionary is empty, then the item store is having an error or is updating
        if not bool(items):
            await message.channel.send('Rust item store is not hot!!!')
        # If we have entries, format and display them
        else:
            embed = discord.Embed()
            # Format the strings for display, this is about the best it gets at the moment as discord does
            # not provide text formatting. So the string looks perfect in console but is off in the chat message
            for item in items:
                item_text = '**' + item + '**'
                embed.add_field(name='**' + item_text + '**', value=items[item], inline=False)
            embed.add_field(name = '**Total Price:** ', value=total_item_price, inline=False)
            item_str = 'Item store: ' + store_url + '\n\n'
            await message.channel.send(item_str, embed=embed)


    # Gets the recipe for a certain item
    elif message.content.lower().startswith('!craftcalc'):
        craft_name = []
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



client.run(keys[0])
