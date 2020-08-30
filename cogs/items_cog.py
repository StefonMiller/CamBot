import math
import re
from time import strftime, gmtime

import discord
from discord.ext import commands
from discord.ext.commands import Cog
import json
import os.path
import CamBot

'''
Cog used to contain commands related to Rust items
'''


# For an input amount of sulfur, display how many rockets, c4, etc you can craft
# @Param sulfur: How much sulfur the user has
# @Param guild: Guild the message was sent in to check for emotes
# @Return: A string containing how many of each explosive they can craft
def sulf_calc(sulfur, guild):
    # Check if the sulfur emote is in the server
    sulfur_emoji = CamBot.check_emoji(guild.emojis, 'sulfur')
    # Initialize the embed with a title using the sulfur emote
    embed_title = 'With ' + str(sulfur) + str(sulfur_emoji) + ' you can craft:'
    embed = discord.Embed(title=embed_title)
    # Create a dict of all other explosives with their sulfur values
    explosive_dict = {'rocket': 1400, 'explosive 5.56 rifle ammo': 25, 'satchel charge': 480,
                      'timed explosive charge': 2200}
    for explosive in explosive_dict.keys():
        # Pad each embed 'row' with an empty field to get a 2-column output
        if (len(embed.fields) % 3) == 1:
            embed.add_field(name="\n\u200b", value="\n\u200b", inline=True)
        explosive_emoji = CamBot.check_emoji(guild.emojis, ''.join(explosive.split('.')))
        embed_name = str(explosive_emoji) + ' x' + str(sulfur // explosive_dict[explosive])
        embed_value = str(sulfur % explosive_dict[explosive]) + str(sulfur_emoji) + ' left over'
        embed.add_field(name=embed_name, value=embed_value, inline=True)
    return embed


class Items(commands.Cog):

    # Constructor
    def __init__(self, client):
        self.client = client

    # Displays composting information
    # @Param args: Item the user wants composting information on
    @commands.command(brief='Composting information',
                      description='Gives composting information for a given item with **composting [itemName]**\nGives '
                                  'composting information on all items with **composting**')
    async def composting(self, ctx, *, args=None):
        cursor = CamBot.cursor
        # If the user didn't enter any item to look up, display composting info for all items
        if not args:
            # Get all data from the composting table
            sql = '''SELECT * FROM composting ORDER BY compost_amount DESC'''
            cursor.execute(sql)
            rows = cursor.fetchall()

            # If there is no data returned, then display an error message
            if not rows:
                embed = discord.Embed(description='No composting data. This should not happen')
                await ctx.send(embed=embed)
                return

            # Loop through each item, format the text, and append it to an array
            str_items = []
            for row in rows:
                str_items.append(row[0].ljust(28) + '\t' + str(row[1]).rjust(6))

            table_lines = CamBot.format_text(str_items, 3)
            await ctx.send('Displaying composting table for all items. Use **!composting [itemName]** '
                           'for data about a specific item :\n')
            # For each line we are trying to output, check if adding it would put us close to the message length
            # limit. If we are approaching it, post the current string and start a new one
            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await ctx.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await ctx.send('```' + output_msg + '```')
        # If the user enters a table name, search for it
        else:
            # Rejoin all args after the command name to pass it onto get_best_match
            item_name = args

            # Once we have the item name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, item_name)

            # Get the item's composting data along with an image and link to its rustlabs page
            sql = '''SELECT * FROM composting WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()

            # If there is no data for the item, return an error message
            if not rows:
                embed_description = 'No composting data for ' + best_item
                embed = discord.Embed(description=embed_description)
                await ctx.send(embed=embed)
                return

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # Display all information in an embed
            title_str = 'Displaying composting data of ' + best_item
            embed = discord.Embed(title=title_str, url=item_url)
            embed.add_field(name='Compost amount', value=rows[0][1], inline=True)
            amount_per_compost = math.ceil(1 / float(rows[0][1]))
            embed.add_field(name='Amount for 1 compost', value=amount_per_compost, inline=True)
            embed.set_thumbnail(url=item_img)
            await ctx.send(embed=embed)

    # Displays harvesting information for a given tool
    # @Param args: The tool the user wants information on
    @commands.command(brief='How many resources a tool can harvest',
                      description='Displays how many resources a given tool harvests from various animals/trees/nodes.'
                                  '\nUse **harvesting [toolName]**')
    async def harvesting(self, ctx, *, args=None):
        # If the user didn't enter any arguments, output the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user entered arguments, get the corresponding tool
        else:
            tool_name = args
            cursor = CamBot.cursor
            connection = CamBot.connection
            # Get the closest item match to what the user entered
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_tool = CamBot.get_string_best_match(item_name_list, tool_name)

            # Get the item's link and image for the embed
            embed_title = 'Displaying harvesting data for the ' + best_tool
            item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(item_sql, (best_tool,))
            item_data = cursor.fetchall()[0]
            item_url = item_data[1]
            item_img = item_data[0]

            # Get item's durability information
            sql = '''SELECT DISTINCT node_name FROM harvesting WHERE item_name = ? ORDER BY resource_name ASC'''
            cursor.execute(sql, (best_tool,))
            harvest_nodes = cursor.fetchall()

            # If there is no data, display an error message and return
            if not harvest_nodes:
                embed_description = best_tool + ' has no harvesting data'
                embed = discord.Embed(embed_description)
                await ctx.send(embed=embed)
                return

            # Create the embed and set the title and URL
            embed = discord.Embed(title=embed_title, url=item_url)
            embed.set_thumbnail(url=item_img)

            num_items = len(harvest_nodes)

            # Loop through the data and add it to the embed
            for node in harvest_nodes:
                if len(embed.fields) >= 24:
                    break
                sql = '''SELECT resource_name, resource_quantity, time FROM harvesting WHERE item_name = ?
                                AND node_name = ?'''
                cursor.execute(sql, (best_tool, node[0]))
                resources = cursor.fetchall()
                embed_value = ''
                for resource in resources:
                    embed_value += resource[1] + ' ' + str(
                        CamBot.check_emoji(ctx.guild.emojis, resource[0])) + '\n'
                embed_value += 'Time: ' + resource[2]
                embed.add_field(name=node[0], value=embed_value, inline=True)
            if num_items > 24:
                num_pages = math.ceil(num_items / 24)
                footer_text = 'Page 1/' + str(num_pages)
                embed.set_footer(text=footer_text)
                msg = await ctx.send(embed=embed)
                # React to the message to set up navigation if there is going to be more than 1 page
                await msg.add_reaction('◀')
                await msg.add_reaction('▶')
                # Insert message data into database file
                sql = '''INSERT INTO harvest_messages (message_id, channel_id, item_name) VALUES (?, ?, ?)'''
                cursor.execute(sql, (msg.id, ctx.channel.id, best_tool))
                connection.commit()

            else:
                # If there is only one page, don't bother setting up a dynamic embed
                await ctx.send(embed=embed)

    # Displays all trades containing a certain item
    # @Param args: The item the user wants trade data on
    @commands.command(brief='Trade information at Outpost and Bandit Camp',
                      description='Displays all trades involving a specific item.\n Use **trades [itemName]**')
    async def trades(self, ctx, *, args=None):
        # If the user didn't enter any item, output the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters an item name, search for it
        else:
            # Get SQLite cursor for database interaction
            cursor = CamBot.cursor
            # Rejoin all args after the command name to pass it onto get_best_match
            item_name = args

            # Once we have the item, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, item_name)

            # Get all trade data for the given item
            sql = '''SELECT * FROM trades WHERE give_item = ? OR receive_item = ? ORDER BY shop_name'''
            cursor.execute(sql, (best_item, best_item))
            trades = cursor.fetchall()

            title_str = 'Displaying all trades involving ' + best_item
            fields = {}

            # If there are no trades, display an error message
            if not trades:
                embed_description = 'You cannot get ' + best_item + ' from a trade'
                embed = discord.Embed(description=embed_description)
                await ctx.send(embed=embed)
                return

            # If there are trades, format the text and append it to a long string
            trade_str = ''
            for trade in trades:
                shop = trade[4]
                try:
                    fields[shop] += '\t' + trade[1] + ' ' + trade[0] + ' for ' + trade[3] + ' ' + trade[2] + '\n'
                except KeyError:
                    fields[shop] = '\t' + trade[1] + ' ' + trade[0] + ' for ' + trade[3] + ' ' + trade[2] + '\n'

            # Send the title string
            await ctx.send(title_str)

            # Format the long trade string to make sure it is within discord character limits
            table_lines = []
            for field in fields:
                table_lines.append(field + '\n' + fields[field])

            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await ctx.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await ctx.send('```' + output_msg + '```')

    # Displays damage stats for a given item
    # @Param args: The item the user wants damage stats for
    @commands.command(brief='Weapon damage information',
                      description='Displays damage values with all ammo for a given weapon.\n Use **damage '
                                  '[weaponName]**')
    async def damage(self, ctx, *, args=None):
        # If the user didn't enter any weapon name, display the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters an item name, search for it
        else:
            # Get SQLite cursor for database interaction
            cursor = CamBot.cursor

            item_name = args

            # Once we have the weapon name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, item_name)

            # Get the damage stats, item image, and item URL for the item returned from get_string_best_match
            sql = '''SELECT DISTINCT ammo_name FROM damage WHERE weapon_name = ?'''
            cursor.execute(sql, (best_item,))
            all_ammo = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # Set the title string and initialize a fields variable to format the embed
            title_str = 'Displaying damage stats for the ' + best_item
            fields = {}

            # If there are no damage stats, display an error message
            if not all_ammo:
                embed_description = best_item + ' has no damage stats'
                embed = discord.Embed(description=embed_description)
                await ctx.send(embed=embed)
                return

            # For each ammo corresponding to the given weapon, extract all of its data from the db and append it to the
            # field dictionary
            for ammo in all_ammo:
                sql = '''SELECT stat_name, stat_value FROM damage WHERE ammo_name = ? AND weapon_name = ?'''
                cursor.execute(sql, (ammo[0], best_item))
                stats = cursor.fetchall()
                stat_str = ''
                for stat in stats:
                    stat_str += stat[0] + ' ' + stat[1] + '\n'
                fields[ammo[0]] = stat_str
            embed = CamBot.format_embed(fields, title_str, item_url, None, item_img, None)
            await ctx.send(embed=embed)

    # Displays mixing table recipes
    # @Param args: The item the user wants a mixing table recipe for
    @commands.command(brief='Mixing table recipes',
                      description='Displays the mixing table recipe for a given item.\n Use **mix [itemName] '
                                  '[numberOfCrafts]**')
    async def mix(self, ctx, *, args=None):
        # Print out a table list if the user doesn't enter a specific one
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters a table name, search for it
        else:
            # Get SQLite cursor for database interaction. Initialize num_crafts to 1
            cursor = CamBot.cursor
            num_crafts = 1
            # Parse the args variable to determine whether or not the user entered an amount to craft
            try:
                # Try to convert the last argument to an int and set it to num_crafts. If that fails then there was
                # no argument for the number
                num_crafts = int(args[-1])
                # Ensure the number entered is valid
                if args[-1] <= 0:
                    await ctx.send(embed=discord.Embed(description='Please enter a valid number'))
                    return
                item_name = args[:-1]
            # If there was an exception, then num_crafts is 1 and the item name is all args passed
            except Exception:
                # Rejoin all args after the command name to pass it onto get_best_match
                item_name = args

            # Once we have the item name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, item_name)

            # Get mixing data on the item
            sql = '''SELECT * FROM mixing WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()

            # If there is no mixing data, display an error message and exit
            if not rows:
                await ctx.send(embed=discord.Embed(description=best_item + ' has no mixing data'))
                return

            # Wait until the empty row case is dealt with before indexing rows to ensure it isn't null
            rows = rows[0]

            # Get the item's image and URL from the database
            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # Set the embed title and append item data to the fields dictionary
            title_str = 'Displaying mixing data of ' + str(num_crafts) + ' ' + best_item
            fields = {}
            for i in range(4):
                ingredient_name = rows[(i * 2) + 1]
                ingredient_quantity = rows[(i * 2) + 2]
                if ingredient_name and ingredient_quantity:
                    key = 'Ingredient ' + str(i + 1)
                    ingredient_emoji = CamBot.check_emoji(ctx.guild.emojis, ingredient_name)
                    value = str(ingredient_emoji) + ' x' + str(num_crafts * int(ingredient_quantity))
                    fields[key] = value

            # Add another field for mixing time after the loop is finished
            key = 'Mixing Time'
            value = str(int(rows[-1]) * num_crafts) + ' seconds'
            fields[key] = value
            # Once all fields have been added, format the embed and display it
            embed = CamBot.format_embed(fields, title_str, item_url, None, item_img, None)
            await ctx.send(embed=embed)

    # Displays durability of buildings/items
    # @Param args: The building the user wants durability stats for
    @commands.command(brief='Durability of a building/item',
                      description='Displays how many explosives/tools it would take to break a building/deployable.\n '
                                  'Use **durability [buildingName]**. Use -h or -s at the end for hard/soft side walls')
    async def durability(self, ctx, *, args=None):
        # If the user didn't enter any arguments, display the command description
        if len(args) == 1:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user entered arguments, look up the building/deployable
        else:
            # Initialize the building side to hard and get the SQLite cursor and connection
            side = 'hard'
            cursor = CamBot.cursor
            connection = CamBot.connection

            # Split args to determine if there was a hard/soft side flag
            args = args.split()
            # Check if there is a -h or -s flag at the end
            if args[-1] == '-h':
                # If there is a hard flag, make the building name all args except first and last
                building_name = ' '.join(args[:-1])
            elif args[-1] == '-s':
                # If there is a soft flag, set the query variable to soft
                building_name = ' '.join(args[:-1])
                side = 'soft'
            else:
                # If there is no flag, make the building name all args except the first
                building_name = ' '.join(args)

            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_building = CamBot.get_string_best_match(item_name_list, building_name)

            # Get the item's link and image for the embed
            embed_title = 'Displaying the durability of a ' + side + ' side ' + best_building
            item_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(item_sql, (best_building,))
            item_data = cursor.fetchall()[0]
            building_url = item_data[1]
            item_img = item_data[0]

            # Get durability data that applies to both sides
            durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = "both" ORDER BY 
                                        tool_sulfur_cost DESC'''
            cursor.execute(durability_sql, (best_building,))
            building_data = cursor.fetchall()

            # If there is not building data, display an error message and exit
            if not building_data:
                embed_description = best_building + ' has no durability'
                embed = discord.Embed(description=embed_description)
                await ctx.send(embed=embed)
                return

            # Get all data from the durability table in the database corresponding to the desired side
            durability_sql = '''SELECT * FROM durability WHERE item_name = ? AND item_side = ? ORDER BY 
                                        tool_sulfur_cost DESC'''
            cursor.execute(durability_sql, (best_building, side))
            building_data.extend(cursor.fetchall())
            # We want a max of 24 fields in an embed, so if there are more than that split the embed and make it
            # dynamic
            num_items = len(building_data)

            # Create the embed and set the title and URL
            embed = discord.Embed(title=embed_title, url=building_url)
            embed.set_thumbnail(url=item_img)

            # Loop through the data and add it to the embed
            for row in building_data:
                if len(embed.fields) >= 24:
                    break
                embed_value = 'Quantity: ' + row[3] + '\nTime: ' + row[4]
                if row[5]:
                    embed_value += '\nSulfur cost: ' + row[5]
                embed.add_field(name=row[2], value=embed_value, inline=True)
            if num_items > 24:
                num_pages = math.ceil(num_items / 24)
                footer_text = 'Page 1/' + str(num_pages)
                embed.set_footer(text=footer_text)
                msg = await ctx.send(embed=embed)
                # React to the message to set up navigation if there is going to be more than 1 page
                await msg.add_reaction('◀')
                await msg.add_reaction('▶')
                # Insert message data into database file
                sql = '''INSERT INTO durability_messages (message_id, channel_id, building, side) VALUES (?, ?, ?, ?)'''
                cursor.execute(sql, (msg.id, ctx.channel.id, best_building, side))
                connection.commit()

            else:
                # If there is only one page, don't bother setting up a dynamic embed
                await ctx.send(embed=embed)

    # Displays experiment tables for each workbench
    # @Param args: The workbench to display the table for
    @commands.command(brief='All blueprints that can be obtained from a given workbench',
                      description='Displays what blueprints can be obtained from a workbench via experimentation.\n '
                                  'Use **experiment [workbenchTier]**')
    async def experiment(self, ctx, *, args=None):
        # If the user didn't enter a workbench tier, display the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            cursor = CamBot.cursor
            # Make sure the user entered a workbench tier
            try:
                tier = int(args)
            except ValueError as e:
                await ctx.send(embed=discord.Embed(description='Please enter a valid workbench tier'))
                return
            # Ensure the tier was either 1, 2, or 3
            if tier == 1 or tier == 2 or tier == 3:
                sql = '''SELECT item_name FROM items WHERE workbench_tier = ?'''
                cursor.execute(sql, (str(tier),))
                # Convert tuples to list
                str_items = list(i[0] for i in cursor.fetchall())
                num_items = len(str_items)
                # Format table items into 5 columns and return each line in a generator
                table_lines = CamBot.format_text(str_items, 3)

                await ctx.send('Displaying the experiment table for **workbench level ' + str(tier)
                               + '**:\n')
                # For each line we are trying to output, check if adding it would put us close to the message length
                # limit. If we are approaching it, post the current string and start a new one
                output_msg = ''
                for line in table_lines:
                    if len(output_msg) + len(line) > 1900:
                        await ctx.send('```' + output_msg + '```')
                        output_msg = ''
                    output_msg += line + '\n'
                await ctx.send('```' + output_msg + '```')
                await ctx.send('The chance of getting one item is 1 in ' + str(num_items) + ' or '
                               + '{0:.2f}'.format((1 / num_items) * 100) + '%')
            else:
                await ctx.send(embed=discord.Embed(description='Please enter a valid workbench tier'))
                return

    # Displays the explosives required to raid a base
    # @Param args: A list of buildings/deployables to raid
    @commands.command(brief='Amount of explosives required to raid a base',
                      description='Calculates the amount of explosives required to raid a certain number of '
                                  'buildings/deployables.\nUse **raidcalc [buildingName] [quantity]**\n'
                                  'Separate different buildings with commas Ex: **raidcalc sheet door 5, stone wall 3'
                                  '**')
    async def raidcalc(self, ctx, *, args=None):
        # If the user didn't enter any buildings, display the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            # Get SQLite cursor for database connectivity
            cursor = CamBot.cursor
            # Split the joined string by comma to separate buildings entered by the user
            buildings = args.split(',')

            total_min_sulfur = 0
            min_sulfur_string = ''
            embed = discord.Embed()
            # For each building block the user entered, get the sulfur cost of raiding it
            for building in buildings:
                # Get the amount of the current building the user wants to blow through
                building_args = building.split()
                # If we encounter a type error when attempting to cast the last argument in our current building, then
                # we assume the user only wants to destroy 1
                num_building = 0
                building_name = []
                try:
                    num_building = int(building_args[-1])
                    for building_arg in building_args:
                        # In the case that we are able to cast the last argument to an int, append all arguments but the
                        # last(which is the number) to the item's name
                        if not building_arg == building_args[-1]:
                            building_name.append(building_arg)
                except ValueError as e:
                    num_building = 1
                    # In the case that we are unable to cast the name to an int, then add all arguments to the item
                    # name
                    for building_arg in building_args:
                        building_name.append(building_arg)
                if num_building <= 0:
                    await ctx.send(embed=discord.Embed(description='Please enter a positive integer'))
                    return

                building_name = ' '.join(building_name)
                # Once we have the building name, search for the best matching one based on the user's search term
                with open('item_names.txt') as file:
                    item_name_list = file.read().splitlines()
                    file.close()
                best_building = CamBot.get_string_best_match(item_name_list, building_name)
                # Get explosive data for the specified building
                sql = '''SELECT tool_name, tool_quantity, tool_sulfur_cost FROM durability WHERE item_name = ? 
                        AND  (item_side = "hard" OR item_side = "both") 
                        AND (tool_name = "Timed Explosive Charge" OR tool_name = "Rocket" OR tool_name = 
                        "Explosive 5.56 Rifle Ammo" OR tool_name = "Satchel Charge");'''
                cursor.execute(sql, (best_building,))
                all_explosives = cursor.fetchall()

                embed_name = 'To get through ' + str(num_building) + ' ' + best_building + ', you would need:'
                # These two variables will be used to calculate the minimum sulfur for the current building item
                min_sulfur = 999999
                lowest_explosive = ''
                # Check if the server has the cambot sulfur emote. If not, display the string 'sulfur' instead of an
                # emote
                sulfur_emote = CamBot.check_emoji(ctx.channel.guild.emojis, 'sulfur')
                # Iterate through the list of all explosives and only get the data of the ones we are looking for
                explosive_cost = ''
                for explosive in all_explosives:
                    explosive_name = explosive[0]
                    explosive_quantity = explosive[1]
                    curr_sulfur = int(explosive[2]) * num_building
                    # Get the item name, quantity, and sulfur cost. Check for the emoji corresponding to the
                    # current explosive
                    explosive_emoji = CamBot.check_emoji(ctx.guild.emojis,
                                                         ''.join(explosive_name.split('.')))
                    curr_cost = '\n' + str(explosive_emoji) + '\tx' + \
                                str(num_building * int(explosive_quantity)) + ' (' + str(curr_sulfur) + \
                                str(sulfur_emote) + ')'

                    explosive_cost += curr_cost
                    if curr_sulfur < min_sulfur:
                        min_sulfur = curr_sulfur
                        lowest_explosive = curr_cost + ' for the ' + building_name
                        if num_building > 1:
                            lowest_explosive += 's'
                embed.add_field(name=embed_name, value=explosive_cost, inline=False)
                # If the minimum didn't change, then the item cannot be broken
                if min_sulfur == 999999:
                    await ctx.send('You cannot break one or more of the items you entered')
                    return
                else:
                    # Add minimum sulfur cost to the total minimum
                    total_min_sulfur += min_sulfur
                    min_sulfur_string += lowest_explosive
            min_name = 'The cheapest path would cost ' + str(total_min_sulfur) + str(sulfur_emote) + ' by using:'
            embed.add_field(name=min_name, value=min_sulfur_string, inline=False)
            await ctx.send(embed=embed)

    # Displays gambling odds at Bandit Camp
    # @Param args: List of outcomes
    @commands.command(brief='Odds of the Bandit Camp wheel',
                      description='Given a series of outcomes for the Bandit Camp wheel, the corresponding percent'
                                  ' chance will be calculated.\nSeparate outcomes with commas, you can also use'
                                  ' ! to denote the negation of a certain outcome Ex: !3 would be the odds of the '
                                  'wheel landing on anything but 3')
    async def gamble(self, ctx, *, args=None):
        # If the user didn't input any arguments, display the general wheel odds
        if not args:
            outcome_text = "```1\t\t\t\t48%\n" \
                           "3\t\t\t\t24%\n" \
                           "5\t\t\t\t16%\n" \
                           "10\t\t\t\t8%\n" \
                           "20\t\t\t\t4%```"
            await ctx.send(embed=discord.Embed(title='Displaying Bandit Camp wheel odds', description=outcome_text))
        # If the user entered arguments, get the odds of that string of outcomes occuring
        else:
            # Hardcoded percentages for the wheel
            percentages = {
                1: .48,
                3: .24,
                5: .16,
                10: .08,
                20: .04
            }
            # Strip all spaces from args
            outcomes = "".join(args.split())
            # Split all outcomes into a list
            outcomes_list = outcomes.split(',')
            percentage = 1
            # For each outcome entered, convert the item to a number and try to look it up in the dictionary
            for outcome in outcomes_list:
                if outcome == '':
                    await ctx.send(embed=discord.Embed(description='You did not enter a number. Use something '
                                                                   'like **!gamble 1,10,3,5**'))
                    return
                # Check if there is an exclamation mark in front of each outcome. If so, the probability should be
                # negated(1-p)
                negate = False
                if outcome[0] == '!':
                    negate = True
                    outcome = outcome[1:]
                # If we can't convert the number to an int, the user didn't enter the outcomes correctly
                try:
                    outcome = int(outcome)
                except Exception as e:
                    await ctx.send(embed=discord.Embed(description='You did not enter a number. Use something like'
                                                                   ' **!gamble 1,1,1,1**'))
                    return
                # If the item doesn't exist in the dictionary, then the user entered something wrong
                try:
                    # If we do get the dictionary value, multiply it by our current percent chance to get the new chance
                    # If there was an !, negate the dictionary value
                    if negate:
                        percentage = percentage * (1 - percentages[outcome])
                    else:
                        percentage = percentage * percentages[outcome]
                except KeyError as k:
                    await ctx.send(embed=discord.Embed(description="You did not enter a valid wheel number. Enter "
                                                                   "1, 3, 5, 10, or 20"))
                    return

            await ctx.send(embed=discord.Embed(description='The chance of the wheel landing on ' +
                                                           ', '.join(outcomes_list) + ' is **' +
                                                           "{:.2f}".format(percentage * 100) + '%**'))

    # Calculates output of recycling an item
    # @Param args: Item name and potentially number of items
    @commands.command(brief='Resource for recycling an item(s)',
                      description='Outputs the resources for recycling a given item.\nUse **recycle [itemName] '
                                  '[itemQuantity]**\nIf you are only calculating for 1 item, you do not have to specify'
                                  ' a quantity')
    async def recycle(self, ctx, *, args=None):
        # If the user did not enter any arguments, display the command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            # Get the SQLite cursor for database connectivity and set num_items to 1
            cursor = CamBot.cursor
            num_items = 1
            args = args.split()
            try:
                # If the user entered an amount, check if it is a valid amount
                num_items = int(args[-1])
                if args[-1] <= 0:
                    await ctx.send(embed=discord.Embed(description='Please enter a valid number'))
                item_name = ' '.join(args[:-1])
            except Exception:
                item_name = ' '.join(args)

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            item = CamBot.get_string_best_match(item_name_list, item_name)

            # Once we find the appropriate item, get its recycle data from the database
            sql = '''SELECT * FROM recycle WHERE item_name = ?'''
            cursor.execute(sql, (item,))
            item_data = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # if we don't get any item data, the item cannot be recycled
            if not item_data:
                await ctx.send(embed=discord.Embed(description=item + ' cannot be recycled'))
                return

            # Output the recycling data. If an output has a drop chance, output its expected value for the number of
            # items being recycled
            title = 'Displaying recycling output for ' + str(num_items) + ' ' + item
            fields = {}
            for item in item_data:
                recycle_name = CamBot.check_emoji(ctx.guild.emojis, item[1])
                recycle_quantity = item[2]
                if recycle_quantity is None:
                    if item[3] is None:
                        recycle_quantity = 1 * num_items
                        recycle_text = str(recycle_name) + ' x' + str(recycle_quantity)
                    else:
                        recycle_percent = int(''.join(filter(str.isdigit, item[3]))) * num_items // 100
                        recycle_text = str(recycle_name) + ' x' + str(recycle_percent) + '(' + item[3] + ')'
                else:
                    recycle_quantity = int(''.join(filter(str.isdigit, recycle_quantity))) * num_items
                    recycle_text = str(recycle_name) + ' x' + str(recycle_quantity)
                fields[recycle_text] = "\n\u200b"

            embed = CamBot.format_embed(fields, title, item_url, None, item_img, None)
            await ctx.send(embed=embed)

    # Displays the loot tables for a given container/NPC
    # @Param args: Name of the container/NPC
    @commands.command(brief='Loot table for a given container/NPC',
                      description='Outputs all items that can drop from a container/NPC along with their respective '
                                  'odds.\nUse **droptable [containerName]**\nFor a list of containers, use '
                                  '**droptable**')
    async def droptable(self, ctx, *, args=None):
        # Get SQLite cursor for database interaction
        cursor = CamBot.cursor
        # Print out a table list if the user doesn't enter a specific one
        if not args:
            embed = discord.Embed()
            # Get all crate names from the sql server and display them
            sql = '''SELECT DISTINCT crate_name FROM droptable'''
            cursor.execute(sql)
            crates = list(i[0] for i in cursor.fetchall())
            embed_value = '\n'.join(crates)
            embed.add_field(name="\n\u200b", value=embed_value, inline=True)
            await ctx.send('This command will display all items dropped from any of the following loot'
                           ' sources along with their respective drop percentages:\n', embed=embed)
        # If the user enters a table name, search for it
        else:
            container_name = args

            # Once we have the crate name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_container = CamBot.get_string_best_match(item_name_list, container_name)

            sql = '''SELECT * FROM droptable WHERE crate_name = ? ORDER BY percent_chance DESC'''
            cursor.execute(sql, (best_container,))
            rows = cursor.fetchall()

            if not rows:
                await ctx.send(embed=discord.Embed(description=best_container + ' has no drop table'))
                return

            str_items = []
            for row in rows:
                str_items.append(row[1].ljust(28) + '\t' + str(row[2]).rjust(6) + '%')

            table_lines = CamBot.format_text(str_items, 3)
            await ctx.send('Displaying drop table for **' + best_container + '**:\n')
            # For each line we are trying to output, check if adding it would put us close to the message length
            # limit. If we are approaching it, post the current string and start a new one
            output_msg = ''
            for line in table_lines:
                if len(output_msg) + len(line) > 1900:
                    await ctx.send('```' + output_msg + '```')
                    output_msg = ''
                output_msg += line + '\n'
            await ctx.send('```' + output_msg + '```')

    # Displays all containers that drop a given item
    # @Param args: Name of the item the user is looking up
    @commands.command(brief='All containers that drop a given item',
                      description='Outputs loot sources that drop a given item.\nUse **lootfrom [itemName]**')
    async def lootfrom(self, ctx, *, args=None):
        # If the user doesn't enter a name, print a command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            cursor = CamBot.cursor
            container_name = args

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, container_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            sql = '''SELECT * FROM droptable WHERE item_name = ? ORDER BY percent_chance DESC'''
            cursor.execute(sql, (best_item,))
            rows = cursor.fetchall()

            if not rows:
                await ctx.send(embed=discord.Embed(description=best_item + ' has no loot sources'))
                return

            str_items = {}
            for row in rows:
                str_items[row[0]] = (str(row[2]) + '%')

            embed_title = 'Displaying drop percentages for ' + best_item
            embed = CamBot.format_embed(str_items, embed_title, item_url, None, item_img, None)
            await ctx.send(embed=embed)

    # Displays stats for a given item
    # @Param args: Name of the item the user is looking up
    @commands.command(brief='General stats for a given item',
                      description='Displays general info as well as HP values and other information.\n'
                                  'Use **stats [itemName]**')
    async def stats(self, ctx, *, args=None):
        # Print out a command description if the user doesn't enter an item name
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            cursor = CamBot.cursor
            search_name = args

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, search_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]
            title = 'Displaying item stats for ' + best_item

            sql = '''SELECT * FROM item_stats WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            stats = cursor.fetchall()

            # Get additional item stats from the item table and add them to the embed if they are not null
            sql = '''SELECT item_identifier, stack_size, despawn_time, health, description 
                            FROM items WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            general_stats = cursor.fetchall()[0]
            names = cursor.description

            desc = general_stats[-1]
            fields = {}
            for i in range(len(general_stats[:-1])):
                if general_stats[i]:
                    fields[names[i][0].replace('_', ' ').title()] = general_stats[i]

            # If the html returned is null, then there are no stats for the item
            if stats is None:
                await ctx.send(embed=discord.Embed(description=best_item + ' has no stats'))
                return

            for stat in stats:
                fields[stat[1]] = stat[2]
            embed = CamBot.format_embed(fields, title, item_url, desc, item_img, None)
            await ctx.send(embed=embed)

    # Displays repair cost for a given item
    # @Param args: Name of the item the user is looking up
    @commands.command(brief='Repair cost for a given item',
                      description='Displays resource cost to repair a given item.\nUse **repair [itemName]**')
    async def repair(self, ctx, *, args=None):
        # Print out a command description if the user doesn't enter an item name
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        # If the user enters an item, search for it. Get a list of all items and find the one matching the user's
        # search term(s)
        else:
            cursor = CamBot.cursor
            search_name = args

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            best_item = CamBot.get_string_best_match(item_name_list, search_name)

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (best_item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            sql = '''SELECT * FROM repair_data WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            repair_data = cursor.fetchall()

            sql = '''SELECT * FROM repair_cost WHERE item_name = ?'''
            cursor.execute(sql, (best_item,))
            repair_costs = cursor.fetchall()

            if not repair_data and not repair_costs:
                await ctx.send(embed=discord.Embed(description=best_item + ' has no repair data'))
                return

            embed_title = 'Displaying repair cost for ' + best_item
            fields = {}
            embed_text = ''
            for cost in repair_costs:
                material_name = cost[1]
                quantity = cost[2]
                emoji = CamBot.check_emoji(ctx.guild.emojis, material_name)

                embed_text += str(emoji) + ' x' + str(quantity) + '\n'
            fields['Repair Cost'] = embed_text

            if repair_data:
                repair_data = repair_data[0]
                fields['Condition Loss'] = repair_data[1]
                fields['Blueprint Required?'] = repair_data[2]

            embed = CamBot.format_embed(fields, embed_title, item_url, None, item_img, None)
            # Output the item's repair data as an embed
            await ctx.send(embed=embed)

    # Displays images for common furnace ratios
    # @Param args: Furnace configuration
    @commands.command(brief='Most efficient furnace layouts for smelting',
                      description='Given a furnace and ore type, the most efficient furnace layouts will be '
                                  'displayed.\nUse **furnaceratios [small/large] [metal.sulfur]**')
    async def furnaceratios(self, ctx, *, args=None):
        # Print out a command description if the user doesn't enter an item name
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))

        else:
            args = args.split()
            # Check if the user entered too many or too few arguments
            if len(args) == 2:
                # If set the size to whatever size the user entered. This is used to find the appropriate images
                if args[0] == 'large':
                    furnace_size = 'lf'
                elif args[0] == 'small':
                    furnace_size = 'sf'
                # If the user didn't enter large or small, then their input is invalid
                else:
                    await ctx.send(embed=discord.Embed(description='You entered an invalid furnace size. '
                                                                   'Please enter \'small\' or \'large\''))

                    return
                # Assign whatever ore the user entered to ore_type, ensuring 'metal' or 'sulfur' were entered
                if args[1] == 'metal' or args[1] == 'sulfur':
                    ore_type = args[1]
                else:
                    await ctx.send(embed=discord.Embed(description='The given ore type is invalid. '
                                                                   'Please enter \'sulfur\' or \'metal\''))
                    return
                # Get all images in the Rust folder containing the appropriate furnace size and ore type
                await ctx.send('Displaying ' + ore_type + ' ratios for a ' + args[0] + ' furnace:\n\n')
                img_path = 'Rust/'
                for img in os.listdir(img_path):
                    if furnace_size in img[0:2]:
                        if ore_type in img:
                            file = discord.File(img_path + img, filename=img)
                            embed = discord.Embed()
                            # Get the wood amount from the image name
                            temp_amts = re.findall(r"[-+]?\d*\.\d+|\d+", img)
                            wood_amt = int(float(temp_amts[0]) * 1000)
                            ore_amt = temp_amts[1]
                            # Wood takes 2 seconds to smelt in any furnace. So the total time is wood * 2
                            time = strftime("%X", gmtime(wood_amt * 2))
                            # Output each appropriate image and the corresponding smelting data
                            img_text = '**' + str(wood_amt) + '** wood' + ' will smelt **' + str(ore_amt) + '** ' \
                                       + args[1] + ' and will take **' + time + '**'
                            embed.set_image(url="attachment://" + img)
                            await ctx.send(img_text, file=file, embed=embed)

            elif len(args) > 2:
                await ctx.send(embed=discord.Embed(description='You entered too many arguments. '
                                                               'Use !furnaceratios for proper syntax'))
                return
            else:
                await ctx.send(embed=discord.Embed(description='You entered too few arguments. '
                                                               'Use !furnaceratios for proper syntax'))
                return

    # Displays how many explosives you can make with a certain amount of sulfur
    # @Param args: Amount of sulfur
    @commands.command(brief='How many explosives can be made with a certain amount of sulfur',
                      description='Given an amount of sulfur, the number of each explosive that can be made will be '
                                  'displayed along with leftover sulfur.\nUse **sulfur [sulfurAmount]**')
    async def sulfur(self, ctx, *, args=None):
        # If len(args) is 1, the user didn't enter an item name
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            num_sulf = -1
            try:
                num_sulf = int(args)
            except Exception as e:
                pass
            # If the user entered an amount, check if it is a valid amount
            if num_sulf <= 0:
                await ctx.send(embed=discord.Embed(description='Please enter a valid number'))
                return
            else:
                # If the user entered a valid amount, call craft_calc with the amount
                await ctx.send('', embed=sulf_calc(num_sulf, ctx.guild))

    # Displays the resource cost for crafting an item
    # @Param args: Item name and potentially number of items
    @commands.command(brief='Resource cost of crafting an item',
                      description='Calculates how many resources it would cost to craft a number of items.\n'
                                  'Use **craftcalc [itemName] [numItems]** If only crafting 1 item, you can leave '
                                  'numItems blank')
    async def craftcalc(self, ctx, *, args=None):
        # If the user doesn't enter any args, print a command description
        if not args:
            await ctx.send(embed=discord.Embed(description=ctx.command.description))
        else:
            cursor = CamBot.cursor
            # Try to convert the last word in the command to an int to test if the user entered an amount
            num_crafts = 1
            try:
                args = args.split()
                # If the user entered an amount, check if it is a valid amount
                num_crafts = int(args[-1])
                if args[-1] <= 0:
                    await ctx.send(embed=discord.Embed(description='Please enter a valid number'))
                item_name = ' '.join(args[:-1])
            except Exception:
                item_name = ' '.join(args)

            # Once we have the building name, search for the best matching one based on the user's search term
            with open('item_names.txt') as file:
                item_name_list = file.read().splitlines()
                file.close()
            item = CamBot.get_string_best_match(item_name_list, item_name)

            if item is None:
                return 'Item not found'

            # Once we find the appropriate item, get its recycle data from the database
            sql = '''SELECT * FROM craftcalc WHERE item_name = ?'''
            cursor.execute(sql, (item,))
            ingredients = cursor.fetchall()

            img_sql = '''SELECT item_img, url FROM items WHERE item_name = ?'''
            cursor.execute(img_sql, (item,))
            data = cursor.fetchall()[0]
            item_img = data[0]
            item_url = data[1]

            # if we don't get any item data, the item cannot be recycled
            if not ingredients:
                await ctx.send(embed=discord.Embed(description=item + ' has no crafting recipe'))
                return

            sulfur_cost = 0
            craft_string = 'Recipe for ' + str(num_crafts) + ' ' + item
            fields = {}
            for ingredient in ingredients:
                output_number = int(ingredient[3])
                # Get quantity of materials, default to 1(if no text), if there is text strip the 'x' or 'ft' from the
                # text and convert it to an int so we can multiply by num_crafts
                quantity = ingredient[2]
                item_name = ingredient[1]
                item_emoji = CamBot.check_emoji(ctx.guild.emojis, item_name)
                total = (int(quantity) * int(num_crafts) // output_number)
                embed_text = str(item_emoji) + ' x' + str(total)
                fields[embed_text] = "\n\u200b"

                if item_name == 'Sulfur':
                    sulfur_cost += (int(quantity) * int(num_crafts) // output_number)
                elif item_name == 'Gunpowder':
                    sulfur_cost += (int(quantity * 2) * int(num_crafts) // output_number)
                elif item_name == 'Explosives':
                    sulfur_cost += (int(quantity * 110) * int(num_crafts) // output_number)

            footer_string = None
            # Check if the sulfur amount is > 0. If so, get the total sulfur amount
            if sulfur_cost > 0:
                footer_string = 'Total sulfur cost: ' + str(sulfur_cost)

            embed = CamBot.format_embed(fields, craft_string, item_url, None, item_img, footer_string)
            await ctx.send(embed=embed)

# Add cogs to bot
def setup(client):
    client.add_cog(Items(client))
