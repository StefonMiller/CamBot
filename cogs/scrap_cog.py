import random
from collections import deque
import discord
from discord.ext import commands
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
    @commands.command(brief='Displays how much scrap you or another user have',
                      description='Shows you how much scrap you currently have. Scrap is gained at a rate of 1'
                                  ' per 10 minutes in a voice channel. Note: Scrap is not shared between servers!',
                      usage='!balance for your own balance\n!balance <@User> for a different user\'s balance.')
    async def balance(self, ctx, user=None):
        if not user:
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
            return

        # Since the user argument is in the form of a mention, the format is <@!ID>. So we remove the <@!> and parse
        # the ID into an it so we can get the member from the ID
        recipient_id = int(user[3:-1])
        recipient = ctx.guild.get_member(recipient_id)

        # Check if the recipient has any scrap on the server
        sql = '''SELECT scrap FROM scrap WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (recipient_id, ctx.guild.id))
        recipient_scrap = CamBot.cursor.fetchall()

        if not recipient_scrap:
            await ctx.send(embed=discord.Embed(description=recipient.name + ' has no scrap on this server yet'))
            return

        recipient_scrap = recipient_scrap[0][0]
        await ctx.send(embed=discord.Embed(description=recipient.name + ' has ' + str(recipient_scrap) + ' scrap'
                                            ' on this server.'))


    # Allows the user to gamble their scrap on the bandit camp wheel
    @commands.command(brief='Allows you to gamble your scrap',
                      description='Allows you to gamble your scrap as you would the Bandit Camp wheel.',
                      usage='!gamble <scrapAmount> <number> to bet scrapAmount on outcome <number>\n'
                            'Ex: !gamble 20 1 would put 20 scrap on 1. For gambling chances, use !banditcamp')
    async def gamble(self, ctx, scrap_amount: int = None, number: int = None):
        if not scrap_amount or not number:
            # If no argument was entered for scrap_amount or number, invoke the help command for gamble
            await ctx.invoke(self.client.get_command('help'), args='gamble')
            return
        # Set of valid numbers on the Bandit Camp wheel
        valid_numbers = [1, 3, 5, 10, 20]
        # Bandit camp wheel numbers and a range out of 100 corresponding to the % chance of the wheel landing on that
        # number
        outcomes = {1: "0-48", 3: "49-72", 5: "73-88", 10: "89-96", 20: "97-100"}
        if number not in valid_numbers:
            await ctx.send(embed=discord.Embed(description='You did not enter a valid number on the wheel.'))
            return
        user_id = ctx.author.id
        server_id = ctx.guild.id
        sql = '''SELECT scrap FROM scrap WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (user_id, server_id))
        current_scrap = CamBot.cursor.fetchall()
        if not current_scrap:
            await ctx.send(embed=discord.Embed(description='You currently don\'t have any scrap in this server to '
                                                           'gamble. Idle in a voice channel for scrap or ask '
                                                           'someone to give you some'))
            return
        # If the user does have a scrap amount on the server, check if the amount they are betting is valid
        current_scrap = current_scrap[0][0]
        if scrap_amount < 0 or scrap_amount > current_scrap:
            await ctx.send(embed=discord.Embed(description='You are trying to bet an invalid amount of scrap. You '
                                                           'only have ' + str(current_scrap) + ' scrap on this '
                                                                                               'server'))
            return

        # Generate a random number to simulate the bandit camp wheel
        spin = random.randint(1, 100)
        end_scrap = 0
        # Get the range of each outcome until we find a match for the generated number.
        for outcome in outcomes:
            # Get the lower and upper bound of the outcome
            outcome_range = outcomes[outcome].split('-')
            # If the spin result is in the given range, we have a match
            if int(outcome_range[0]) <= spin <= int(outcome_range[1]):
                # If the user picked the right number, print out a win message and update their scrap value
                if number == outcome:
                    end_scrap = current_scrap + (outcome * scrap_amount)
                    await ctx.send(embed=discord.Embed(description='The wheel landed on ' + str(outcome) + '. You won '
                                                                   + str(outcome * scrap_amount) +
                                                                   ' scrap!\nYour balance is now ' + str(end_scrap)))

                # If the user lost, display a lose message and deduct the scrap amount from their account
                else:
                    end_scrap = current_scrap - scrap_amount
                    await ctx.send(embed=discord.Embed(description='The wheel landed on ' + str(outcome) + '. You '
                                                                    'lost ' + str(scrap_amount) +
                                                                   ' scrap.\nYour balance is now ' + str(end_scrap)))
        sql = '''UPDATE scrap SET scrap = ? WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (end_scrap, user_id, server_id))
        CamBot.connection.commit()

        # After the user gambles, check if they have earned a promotion
        await CamBot.check_for_promotion(end_scrap, ctx.author, ctx.guild)

    # Displays user's current scrap balance
    @commands.command(brief='Gives scrap to another member of the server',
                      description='Allows you to give some of your scrap to another person in the server.',
                      usage='!give <@User> <scrapAmount>')
    async def give(self, ctx, user=None, scrap_amount: int = None):
        if not scrap_amount or not user:
            # If no argument was entered for user or scrap_amount, invoke the help command for give
            await ctx.invoke(self.client.get_command('help'), args='gamble')
            return

        # Get how much scrap the user has in the current server
        sql = '''SELECT scrap FROM scrap WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (ctx.author.id, ctx.guild.id))
        current_scrap = CamBot.cursor.fetchall()

        if not current_scrap:
            await ctx.send(embed=discord.Embed(description='You currently don\'t have any scrap in this server'))
            return

        # If the user does have a scrap amount on the server, check if the amount they are betting is valid
        current_scrap = current_scrap[0][0]
        if scrap_amount < 0 or scrap_amount > current_scrap:
            await ctx.send(embed=discord.Embed(description='You are trying to bet an invalid amount of scrap. You '
                                                           'only have ' + str(current_scrap) + ' scrap on this '
                                                                                               'server'))
            return

        # If the scrap amount is valid, subtract that amount from the user giving the scrap
        sql = '''UPDATE scrap SET scrap = ? WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, ((current_scrap - scrap_amount), ctx.author.id, ctx.guild.id))
        CamBot.connection.commit()
        current_scrap = current_scrap - scrap_amount


        # Since the user argument is in the form of a mention, the format is <@!ID>. So we remove the <@!> and parse
        # the ID into an it so we can get the member from the ID
        recipient_id = int(user[3:-1])
        recipient = ctx.guild.get_member(recipient_id)

        # Check if the recipient has any scrap on the server
        sql = '''SELECT scrap FROM scrap WHERE member_id = ? AND server_id = ?'''
        CamBot.cursor.execute(sql, (recipient_id, ctx.guild.id))
        recipient_scrap = CamBot.cursor.fetchall()

        # If the user doesn't have any scrap, create an entry for them and assign them the 'poor' role
        if not recipient_scrap:
            recipient_scrap = scrap_amount

        else:
            recipient_scrap = recipient_scrap[0][0]
            # If the user has a scrap value, add the scrap they were given
            recipient_scrap = recipient_scrap + scrap_amount

        # Update the user's scrap value
        sql = '''INSERT OR REPLACE INTO scrap(member_id, server_id, scrap) VALUES (?, ?, ?)'''
        CamBot.cursor.execute(sql, (recipient_id, ctx.guild.id, recipient_scrap))
        CamBot.connection.commit()

        await ctx.send(embed=discord.Embed(description='You gave ' + recipient.name + ' ' + str(scrap_amount) +
                                           ' scrap(' + str(recipient_scrap) + ' total).\nYour balance is '
                                            + str(current_scrap) + ' scrap.'))
        await CamBot.check_for_promotion(current_scrap, ctx.author, ctx.guild)
        await CamBot.check_for_promotion(recipient_scrap, recipient, ctx.guild)

    # Displays info on scrap and gaining it
    @commands.command(brief='General information on the scrap system',
                      description='Gives information on how the scrap system works(Roles, amounts).',
                      usage='!scrapinfo')
    async def scrapinfo(self, ctx):
        embed_description = 'CamBot\'s scrap system awards users 1 scrap for every 10 minutes they are in a voice ' \
                            'channel. Roles are assigned automatically when you reach a new scrap level. You can ' \
                            'earn the following roles:'

        # Get role list
        sql = '''SELECT role_name, role_cost FROM roles'''
        CamBot.cursor.execute(sql)
        roles = dict(i for i in CamBot.cursor.fetchall())
        # Since each role's threshold is assigned to the previous role for promotions, create a deque to pop the last
        # value and insert a 0 in the front
        role_deque = deque(roles.values())
        role_deque.pop()
        role_deque.appendleft(0)
        # Once the deque is done, create a new dictionary
        roles = {list(roles.keys())[i]: role_deque[i] for i in range(len(roles))}
        # Format an embed with the description and a field for every role and then display it.
        embed = CamBot.format_embed(roles, None, None, embed_description, None, None)
        await ctx.send(embed=embed)


# Add cogs to bot
def setup(client):
    client.add_cog(Scrap(client))
