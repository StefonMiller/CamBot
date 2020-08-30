from datetime import datetime
import discord
from discord.ext import commands
from discord.ext.commands import Cog
import json
import os.path
import CamBot
from updater import update_database

'''
Cog used to contain commands related to the bot/server settings
'''


# Gets the elapsed time from start_time until now
# @Param start_time: Initial time, defaults to the time when the bot started
# @Return Formatted string representing the elapsed time
def get_uptime(start_time):
    curr_time = datetime.now()
    elapsed_time = curr_time - start_time
    seconds = elapsed_time.seconds
    hours = seconds // 3600
    if hours > 1:
        seconds -= hours * 3600
    minutes = seconds // 60
    if minutes > 1:
        seconds -= minutes * 60
    output = str(elapsed_time.days) + 'd, ' + str(hours) + 'h, ' + str(minutes) + 'm, ' + str(seconds) + 's'
    return output


# Checks if the author of a message has administrative privileges on the server
def check_role(ctx):
    return ctx.message.author.permissions_in(ctx.channel).administrator


class Settings(commands.Cog):

    # Constructor
    def __init__(self, client):
        self.client = client

    # Commands

    # Custom help command displayed in an embed
    # @Param args: Any arguments entered after the command name
    @commands.command(brief='Displays this message', description='Displays all commands and a short description of '
                                                                 'them', aliases=['cambot'])
    async def help(self, ctx, *, args=None):
        # If the user entered a command they want info on, look it up and display the command description
        if args:
            # Look up the command given by the user
            command_name = ''.join(args)
            command = self.client.get_command(command_name)
            # If the command doesn't exist, inform the user to use the help command w no args
            if not command:
                title_text = 'Command ' + ctx.prefix + command_name + ' not found'
                description_text = 'For a list of commands, use ' + ctx.prefix + 'help'
            # If the command exists, display its information
            else:
                title_text = 'Displaying information on ' + ctx.prefix + command_name
                description_text = command.description
            embed = discord.Embed(title=title_text, description=description_text)
            await ctx.send(embed=embed)
        else:
            # If there are no other arguments besides help, display a list of commands
            prefix = ctx.prefix
            description_text = 'For more info on a specific command use ' + prefix + 'help [command]'
            embed = discord.Embed(title='Displaying all CamBot commands:', description=description_text)
            # Get all cogs from the discord Bot object
            cog_list = self.client.cogs
            # For each cog loaded, get all commands and display them
            for cog in cog_list:
                cog_commands = ''
                for command in cog_list[cog].get_commands():
                    # Don't display info on hidden commands
                    if not command.hidden:
                        cog_commands += prefix + command.name + ' - ' + command.brief + '\n'
                if cog_commands == '':
                    cog_commands = 'No commands here yet!'
                embed.add_field(name=cog, value=cog_commands, inline=False)
            await ctx.send(embed=embed)

    # Changeprefix changes the server's prefix to a specified sequence of characters
    # @Check check_role: Command can only be run by server administrators
    # @Param prefix: Prefix the user wants to change to
    @commands.command(brief='Changes the server prefix',
                      description='This command changes the server prefix to any character sequence without spaces. '
                                  'If spaces are entered, only the first character sequence will be used.\nUse '
                                  '**changeprefix [prefix]**')
    @commands.check(check_role)
    async def changeprefix(self, ctx, prefix: str = None):
        if not prefix:
            embed = discord.Embed(description=ctx.command.description)
            await ctx.send(embed=embed)
            return
        # Open the prefix json file and change the prefix to prefix. Then write it back to the file
        prefix_path = os.path.dirname(__file__) + '/../server_prefixes.json'
        with open(prefix_path, 'r') as f:
            prefixes = json.load(f)

        prefixes[str(ctx.guild.id)] = prefix

        with open(prefix_path, 'w') as f:
            json.dump(prefixes, f)

        await ctx.send('Server prefix changed to ' + prefix)

    # Displays information about the bot
    @commands.command(brief='Displays information about CamBot', description='This command displays information'
                                                                             ' on CamBot\'s uptime and the number of '
                                                                             'servers it is connected to')
    async def info(self, ctx):
        # Get the amount of time CamBot has been running for
        uptime = get_uptime(CamBot.get_start_time())
        # Get the number of servers CamBot is connected to
        num_servers = len(self.client.guilds)
        embed = discord.Embed(title="Cambot provides useful data for skins/items in Rust",
                              description="[Add Cambot to your server](https://discord.com/oauth2/authorize?c"
                                          "lient_id=684058359686889483&permissions=8&scope=bot)")

        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
        embed.add_field(name="Connected servers", value=num_servers, inline=True)
        # Set the embed thumbnail to CamBot's current avatar picture
        avatar = self.client.user.avatar_url
        embed.set_thumbnail(url=avatar)
        await ctx.send(embed=embed)

    # Adds all emojis to the server. If there is no room, it lets the user know
    @commands.command(brief='Adds all of CamBot\'s emojis to the server',
                      description='This command adds all(~30) emojis used by CamBot to the server. If there are not'
                                  ' enough emoji slots, CamBot will tell you how many emoji slots you need.')
    async def addemojis(self, ctx):
        result = await CamBot.add_emojis(ctx.guild)
        await ctx.send(result)

    # Removes all emojis from the server
    @commands.command(brief='Removes all of CamBot\'s emojis from the server',
                      description='This command removes all of CamBot\'s emojis from the server')
    async def removeemojis(self, ctx):
        result = await CamBot.remove_emojis(ctx.guild)
        await ctx.send(result)

    # Performs a full update of the database from which CamBot pulls data
    # @check: Only owner of the bot can execute this command
    @commands.command(hidden=True)
    @commands.is_owner()
    async def update(self, ctx):
        # CamBot.tweet('Cambot is down for updates and will be available again in ~20 minutes.')
        output = update_database()
        await ctx.send(output)


# Add cogs to bot
def setup(client):
    client.add_cog(Settings(client))
