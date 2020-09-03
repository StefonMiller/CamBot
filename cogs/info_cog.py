import random

import discord
from discord.ext import commands
from discord.ext.commands import Cog
import json
import os.path
import CamBot

'''
Cog used to contain commands related to Game info
'''


# Gets the status of all servers the CamBot is dependent on
# @Return: List of servers and connection stats
def get_status():
    # Fill an array with each server we want to test
    import requests
    server_names = ['https://www.battlemetrics.com', 'https://rust.facepunch.com/blog/', 'https://www.rustlabs.com/',
                    'https://rustafied.com/', 'https://steamcharts.com/']

    server_dict = {}
    for server in server_names:
        connection_status = requests.head(server)
        if connection_status.status_code == 200 or 301:
            server_dict[server] = '🟢 Online'
        else:
            server_dict[server] = '🔴 Offline'
    return server_dict


# Returns the player count of a certain server URL on Battlemetrics.com
# @Param server_url: - url of the server we want the player count of
# @Return: - number of players on the server
def server_pop(server_url):
    server_html = CamBot.get_html(server_url)
    pop = server_html.find('dt', string='Player count').find_next_sibling('dd')
    return pop.text


class Info(commands.Cog):

    # Constructor
    def __init__(self, client):
        self.client = client

    # Displays rust bind info
    # @Param args: The kind of info on binds the user wants
    @commands.command(brief='Displays information on Rust keybinds',
                      description='Displays information on rust binds in 4 categories: Commands, Keys, Gestures, '
                                  'and Popular Binds',
                      usage='!binds commands displays all commands you can bind to a key\n'
                            '!binds keys displays all keys you can bind commands to\n'
                            '!binds gestures displays all gestures you can bind to a key and how to do so\n'
                            '!binds popular displays the most popular/useful keybinds')
    async def binds(self, ctx, *, args=None):
        # If the user didn't enter any args display the command desc
        if not args:
            # If no argument was entered for prefix, invoke the help command for binds
            await ctx.invoke(self.client.get_command('help'), args='binds')
            return
        else:
            # Displays all console commands you can use
            if args.lower() == 'commands':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('bind_commands.txt') as file:
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
                await ctx.send(
                    'Displaying all commands you can bind in console. You can bind multiple commands to a key by '
                    'seperating them with a ;. Additionally, adding a + before a command will only activate it '
                    'while the key is held down', embed=embed)
            # Displays all keys currently bindable in Rust
            elif args.lower() == 'keys':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('bind_keys.txt') as file:
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
                await ctx.send("Displaying all supported keys you can bind commands to. In Rust console, "
                               "enter **bind [key] [command]**\n", embed=embed)
            elif args.lower() == 'gestures':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('bind_gestures.txt') as file:
                    key_list = file.read().splitlines()
                    file.close()
                # Create embed for output
                embed = discord.Embed()
                gestures_text = "```"
                for key in key_list:
                    gestures_text += key + '\n'
                gestures_text += '```'
                await ctx.send("Displaying all gestures. In Rust console, enter **bind [key] \" gesture"
                               " [gestureName]\"** Make sure you include the quotes!\n" + gestures_text)
            elif args.lower() == 'popular':
                # Open text file and get all lines. The txt file is structured so the first line is an embed title and
                # the next is the embed value
                with open('binds_popular.txt') as file:
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
                await ctx.send(
                    'Displaying the most popular binds', embed=embed)
            else:
                await ctx.send(embed=discord.Embed(description='You did not enter a valid command. Use **binds keys,'
                                                               ' gestures, commands, or popular**'))

    # Displays player info for a given game
    # @Param args: The game the user wants to look up
    @commands.command(brief='Displays player stats for a given game',
                      description='Displays how many players are currently online for a given game.',
                      usage='!steamstats <gameName>')
    async def steamstats(self, ctx, *, args=None):
        # If the user didn't enter any args, display the command desc
        if not args:
            # If no argument was entered for prefix, invoke the help command for steamstats
            await ctx.invoke(self.client.get_command('help'), args='steamstats')
            return
        else:
            # Look up the game name on steamcharts.com. Encode URL before navigation
            game_name = args
            game_name = game_name.replace(' ', '+')
            game_name = game_name.replace('&', '%26')
            game_name = game_name.replace('?', '%3F')
            url = 'https://steamcharts.com/search/?q=' + game_name

            # Get html data for the given url and get the table containing all games
            search_html = CamBot.get_html(url)
            table = search_html.find('tbody')
            # If there are no results, display an error message
            if not table:
                description = game_name + ' has no player data'
                await ctx.send(embed=discord.Embed(description=description))

            rows = table.find_all('tr')
            results = {}

            # For each row add the game data to a dictionary
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

            # From all games on the results page, find the closest one to what the user entered
            best_game = CamBot.get_string_best_match(results.keys(), game_name)

            # Get the best game in the dictionary and output its data
            data = results[best_game]
            fields = {'Current Players': data[0], 'Month Average': data[1], 'Monthly Gain/Loss': data[2]}
            title = 'Displaying steam player data for ' + best_game
            embed = CamBot.format_embed(fields, title, None, None, None, None)
            await ctx.send(embed=embed)

    # Displays current players on a given Rust server
    # @Param args: The game the user wants to look up
    @commands.command(brief='Outputs player count for a given Rust server',
                      description='Displays how many players are currently on a given Rust server.',
                      usage='!serverpop for info on Bloo Lagoon and Rustafied Trio\n'
                            '!serverpop <serverName> for information on any server')
    async def serverpop(self, ctx, *, args=None):
        # If there are no args, display server info for bloo lagoon and rustafied trio
        if not args:
            # Search the specific servers we frequent
            await ctx.send('Rustafied Trio currently has ' + server_pop(
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
            bm_html = CamBot.get_html(bm_url)
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
            best_match = CamBot.get_best_match(servers, server_name)
            # If get_best_match returns an empty string, there was no matching server
            if best_match == '':
                await ctx.send(embed=discord.Embed(description='Server not found'))
            # If we did find a server, get the link from the html element and get its pop via server_pop
            else:
                link = best_match['href']
                serv_name = best_match.text
                url = 'https://battlemetrics.com' + link
                await ctx.send(embed=discord.Embed(description=serv_name + ' currently has ' +
                                                               server_pop(url) + ' players online'))

    # Displays latest rustafied news article
    @commands.command(brief='Displays the newest Rustafied news article',
                      description='Gets the latest Rustafied news article and posts a link to it',
                      usage='!rustnews')
    async def rustnews(self, ctx):
        # Navigate to Rustafied.com and get the title and description of the new article
        title, desc = CamBot.get_news('https://rustafied.com')
        # Embed a link to the site with the retrieved title and description
        embed = discord.Embed(title=title, url='https://rustafied.com', description=desc)
        await ctx.send('Here is the newest Rustafied article:', embed=embed)
        # Displays latest rustafied news article

    @commands.command(brief='Displays the newest Rust DevBlog',
                      description='Gets the latest devblog and posts a link to it',
                      usage='!devblog')
    async def devblog(self, ctx):
        # Outputs a link to of the newest rust devblog. I am using an xml parser to scrape the rss feed as the
        # website was JS rendered and I could not get selerium/pyqt/anything to return all of the html that I needed
        title, devblog_url, desc = CamBot.get_devblog('https://rust.facepunch.com/rss/blog', 'Update', 'Community')
        embed = discord.Embed(title=title, url=devblog_url, description=desc)
        await ctx.send('Newest Rust Devblog:', embed=embed)

    # Displays a pic of Cammy
    @commands.command(brief='Posts a picture of the inspiration for this bot',
                      description='Posts a HOT picture of physical embodiment of CamBot',
                      usage='!campic')
    async def campic(self, ctx):
        # Posts a random picture from a given folder
        img_path = 'Cam/'
        pics = []
        # Get the filenames of all images in the directory
        for fileName in os.listdir(img_path):
            pics.append(fileName)

        # Select a random filename from the list and upload the corresponding image
        rand_pic = random.choice(pics)
        file = discord.File(img_path + rand_pic, filename=rand_pic)
        await ctx.send(file=file)

    # Displays the status of all of CamBot's dependent servers
    @commands.command(brief='Displays the status of CamBot\'s dependent servers',
                      description='This command will show status lights for all of the servers CamBot pulls data from',
                      usage='!status')
    async def status(self, ctx):
        statuses = get_status()
        embed = discord.Embed(title='Displaying staus of all dependent servers:')
        # Display statuses in an embed
        for status in statuses:
            embed.add_field(name=status, value=statuses[status], inline=False)

        await ctx.send(embed=embed)


# Add cogs to bot
def setup(client):
    client.add_cog(Info(client))
