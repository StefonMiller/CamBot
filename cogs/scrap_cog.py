import random

import discord
from discord.ext import commands
from discord.ext.commands import Cog
import json
import os.path
import CamBot

'''
Cog used to contain commands related to Scrap
'''


# Returns the player count of a certain server URL on Battlemetrics.com
# @Param server_url: - url of the server we want the player count of
# @Return: - number of players on the server
def server_pop(server_url):
    server_html = CamBot.get_html(server_url)
    pop = server_html.find('dt', string='Player count').find_next_sibling('dd')
    return pop.text


class Scrap(commands.Cog):

    # Constructor
    def __init__(self, client):
        self.client = client

    # Displays user's current scrap balance
    @commands.command(brief='Displays your current scrap balance',
                      description='Shows you how much scrap you currently have. Scrap is gained at a rate of 1'
                                  ' per 10minutes in a voice channel. Note: Scrap is not shared between servers!',
                      usage='!balance')
    async def balance(self, ctx):
        # Get how much scrap the user has in the current server
        sql = '''SELECT scrap FROM scrap WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (ctx.author.id, ctx.guild.id))
        current_scrap = CamBot.cursor.fetchall()

        if not current_scrap:
            await ctx.send(embed=discord.Embed(description='You currently don\'t have any scrap in this server'))
            return

        # If the user does have a scrap amount on the server, display it
        current_scrap = current_scrap[0][0]
        await ctx.send(embed=discord.Embed(description='You currently have ' + str(current_scrap) + ' scrap on ' +
                                                       ctx.guild.name))


# Add cogs to bot
def setup(client):
    client.add_cog(Scrap(client))
