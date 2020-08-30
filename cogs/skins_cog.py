import sqlite3
from steam_community_market import Market, AppID
import CamBot
import discord
import pyotp
import requests
from discord.ext import commands
from discord.ext.commands import Cog
import json
import os.path

'''
Cog used to contain commands related to Rust skins
'''


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


# Gets all skin data using Bitskins API
# @Return: A dictionary filled with skin data for every item
def get_skin_prices():
    # Open file containing API keys
    with open('bitskins_keys.txt') as f:
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


# Generates the initial embed for the skinlist command and inserts all other pages into the
# skinlist_messages database
# @Param sorted_by_prices: List of 10 skins sorted by a certain price
# @Param channel: Channel to output the embed
async def display_skinlist_embed(sorted_by_price, channel, title_string, embed_name):
    # Get the link for each item and output it in an embed
    i = 0
    cursor = CamBot.cursor
    connection = CamBot.connection
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


# Cross references skins of a certain type with a master list of skins and their current prices retrieved from
# Bitskins API. This is used to get all skins of skin_type and their current prices, which will then be sorted
# to display aggregate data on said skins
def cross_reference_skins(skin_type=''):
    if skin_type == '':
        cursor = CamBot.cursor
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


# Gets all skins of a certain type
# @Param type: Type of skin to look up
# @Return: The category matching best matching type and the resulting skins of that category
def get_skins_of_type(skin_type):
    cursor = CamBot.cursor
    # Get the skin category closest to type
    with open('skin_types.txt') as file:
        skin_type_list = file.read().splitlines()
        file.close()
    best_skin = CamBot.get_string_best_match(skin_type_list, skin_type)
    # Select all skins of that category
    sql = "SELECT skin_name, link, initial_price, release_date, skin_img FROM skin WHERE skin_type = \"" + \
          best_skin + "\""
    cursor.execute(sql)
    data = cursor.fetchall()
    # Return data for skins of that category and the category name
    return data, best_skin


class Skins(commands.Cog):

    # Constructor
    def __init__(self, client):
        self.client = client

    # Displays aggregate skin data
    # @Param args: Arguments to determine the data the user wants
    @commands.command(brief='Displays the top 10 skins in a certain category',
                      description='This command displays aggregate skin data. It will output the top 10 cheapest, '
                                  'most expensive, least proitable, or most profitable skins on the market currently\n'
                                  'Use **skinlist -c, -e, -lp, or -mp [itemType]** Ex: **skinlist -e assault rifle**\n'
                                  'You can also get all skins for an item type with **skinlist [itemType]**')
    async def skinlist(self, ctx, *, args=None):
        # If the user didn't enter any arguments, display the command desc
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            # If the user entered arguments, split them
            args = args.split()
        # Check the first argument to determine what function to perform
        if args[0] == '-c':
            search_type = ' '.join(args[1:])
            # If there are no arguments after -c, then display the cheapest skins of all categories
            if search_type == '':
                # Get all items names and their prices from Bitskins API
                skin_price_list = get_skin_prices()
                # Sort the returned dictionary by price and take the 10 lowest values
                sorted_by_price = {k: v for k, v in sorted(skin_price_list.items(), key=lambda ite: float(ite[1]))[:10]}
                # Once we have a sorted dictionary, display the data and add it to the database
                await display_skinlist_embed(sorted_by_price, ctx.channel,
                                             'Displaying the 10 cheapest skins on the market:', 'Price')

            else:
                # Get a list of objects containing all items of search_type
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.cp))[:10]
                msg_text = 'Displaying the 10 cheapest skins for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, ctx.channel, msg_text, 'Price')
        elif args[0] == '-e':
            search_type = ' '.join(args[1:])
            # If there are no arguments after -e, then display the cheapest skins of all categories
            if search_type == '':
                # Get item names and prices of all items using Bitskins API
                skin_price_list = get_skin_prices()
                # Sort the list by price and take the 10 highest values
                sorted_by_price = {k: v for k, v in sorted(skin_price_list.items(), key=lambda ite: float(ite[1]),
                                                           reverse=True)[:10]}
                await display_skinlist_embed(sorted_by_price, ctx.channel,
                                             'Displaying the 10 most expensive skins on the market:', 'Price')

            else:
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 most expensive skins for
                # skin_type in this case. This is pretty much the same as -c, except we reverse the sorting
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.cp), reverse=True)[:10]
                msg_text = 'Displaying the 10 most expensive skins for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, ctx.channel, msg_text, 'Price')

        elif args[0] == '-lp':
            search_type = ' '.join(args[1:])
            # If there are no arguments after -lp, then display the least profitable of all categories
            if search_type == '':
                # Get a list of objects containing all items in rust. I cannot simply use the Bitskins API for this
                # like with -c and -e since I need current price which can only be found in my database. Thus,
                # I have to combine my database and Bitskins to get the %profit
                skin_list = cross_reference_skins()
                # Once we have the skins, sort them by percent profit and take the 10 lowest values
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc))[:10]
                await display_skinlist_embed(sorted_by_price, ctx.channel,
                                             'Displaying the 10 skins with the worst profit:', 'Percent change')

            else:
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc))[:10]
                msg_text = 'Displaying the 10 skins with the worst profit for ' + best_skin + 's:'
                await display_skinlist_embed(sorted_by_price, ctx.channel, msg_text, 'Percent change')

        elif args[0] == '-mp':
            search_type = ' '.join(args[1:])
            # If there are no arguments after -lp, then display the least profitable of all categories
            if search_type == '':
                # Get a list of objects containing all items in rust. I cannot simply use the Bitskins API for this
                # like with -c and -e since I need current price which can only be found in my database. Thus,
                # I have to combine my database and Bitskins to get the %profit
                skin_list = cross_reference_skins()
                # Once we have the list of skins, sort them by %profit and take the 10 highest values
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc), reverse=True)[:10]
                await display_skinlist_embed(sorted_by_price, ctx.channel,
                                             'Displaying the 10 skins with the best profit:', 'Percent change')

            else:
                skin_list, best_skin = cross_reference_skins(search_type)
                # Once we have a list of sorted objects, diplay the first 10. These will be the 10 cheapest skins for
                # skin_type in this case
                sorted_by_price = sorted(skin_list, key=lambda x: float(x.pc), reverse=True)[:10]
                msg_text = 'Displaying the 10 skins with highest returns for ' + best_skin + ':'
                await display_skinlist_embed(sorted_by_price, ctx.channel, msg_text, 'Percent change')

        else:
            skin_type = ' '.join(args)
            data, best_skin = get_skins_of_type(skin_type)
            # Theoretically, there should always be a match but if there isn't exit the command and let the user know
            if not data:
                await ctx.send(embed=discord.Embed(description='No skin data found for the given skin. '
                                                               'Use **!skinlist [skinname]**\n'))
                return
            else:
                desc = ''
                # Once we have the data, display it in an embed. Since there will be potentially hundreds of skins,
                # do not display one skin per line. Instead, separate them with |s.
                await ctx.send('Displaying all skins for **' + best_skin + '**:')
                for d in data:
                    if len(desc) + len('[' + d[0] + '](' + d[1] + ') | ') >= 2000:
                        embed = discord.Embed(description=desc)
                        await ctx.send(embed=embed)
                        desc = ""
                    else:
                        desc += '[' + d[0] + '](' + d[1] + ') | '
                embed = discord.Embed(description=desc)
                await ctx.send(embed=embed)

    # Displays all information on a given skin name
    # @Param args: Name of the skin the user wants info on
    @commands.command(brief='Displays information for a given skin',
                      description='This command displays price and release information for a given skin.\n'
                                  'Use **skindata [skinName]**\n**NOTE:** All skin prices/dates are estimates. Initial'
                                  ' price information is very innacurate for skins released a long time ago')
    async def skindata(self, ctx, *, args=None):
        # If the user didnt' enter any args, display the command description
        if not args:
            # Search the specific servers we frequent
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If there is a server argument, add any arguments after !serverpop to the server name
        else:
            # Get SQLite cursor for database interaction
            cursor = CamBot.cursor
            # If the user entered an item name, ensure it is all in one string and search for it in the database
            skin_name = args
            # Open a text file containing a list of all rust item names and find the best match
            with open('skins.txt') as file:
                skin_name_list = file.read().splitlines()
                file.close()
            best_skin = CamBot.get_string_best_match(skin_name_list, skin_name)

            # Once we get the best matching item string, query the item's data from the SQL server. I originally
            # queried data matching the search term using the %like% keyword and then used best_match to get the
            # best item from the query's results. However, this often led to searches that didn't return any items
            # which is not what I wanted. So I decided to reverse them at the cost of performance
            sql = "SELECT * FROM skin WHERE skin_name = \"" + best_skin + "\""
            cursor.execute(sql)
            data = cursor.fetchall()[0]
            # Theoretically, there should always be a match but if there isn't exit the command and let the user know
            if not data:
                await ctx.send(embed=discord.Embed(description='No skin data found for ' + best_skin))
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
                await ctx.send(embed=discord.Embed(description=name + ' has no market price data at the moment. '
                                                                      'This probably means the skin came out this '
                                                                      'week and cannot be placed on the market at '
                                                                      'this time.'))
                return
            # Attempt to get the percent change, and if we divide by 0 somehow, just set the percent to 0
            try:
                percent_change = "{:.2f}".format(((current_price - skin_initial_price) / skin_initial_price) * 100)
            except ZeroDivisionError:
                percent_change = 0

            # Dipsplay the data and an image for the given item
            title = 'Displaying skin data for ' + name
            fields = {'Release Date': skin_initial_date, 'Initial Price': '$' + str(skin_initial_price),
                      'Current Price': '$' + str(current_price),
                      'Price Difference': '$' + '{0:.2f}'.format(current_price - skin_initial_price),
                      'Percent Change': str(percent_change) + '%', 'Skin For': skin_type}
            embed = CamBot.format_embed(fields, title, skin_url, None, skin_img, None)
            await ctx.send(embed=embed)

    # Displays the skins currently in the Rust item store
    @commands.command(brief='Displays the skins currently for sale on Steam',
                      description='This command displays the current skins for sale along with a predicted price for '
                                  'each one. The predicted price may not be correct!')
    async def rustskins(self, ctx):
        cursor = CamBot.cursor
        connection = CamBot.connection
        items, total_item_price = CamBot.get_rust_items('https://store.steampowered.com/itemstore'
                                                        '/252490/browse/?filter=All')
        # If the dictionary is empty, then the item store is having an error or is updating
        if not bool(items):
            await ctx.send(embed=discord.Embed(description='Rust item store is not hot!!!'))
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
            msg = await ctx.send(embed=embed)
            # Insert all other items into the SQL database with corresponding message and channel ids
            for item in items:
                try:
                    sql = "INSERT INTO item_store_messages (message_id, channel_id, item_name, starting_price, " \
                          "predicted_price, store_url) VALUES(?, ?, ?, ?, ?, ?)"
                    temp_pr = str(item.pr)
                    val = (msg.id, ctx.channel.id, item.n, item.p, temp_pr, item.im)
                    cursor.execute(sql, val)
                    connection.commit()
                except Exception as e:
                    pass
            # React to the message to set up navigation
            await msg.add_reaction('◀')
            await msg.add_reaction('▶')

# Add cogs to bot
def setup(client):
    client.add_cog(Skins(client))
