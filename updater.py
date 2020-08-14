import sqlite3
import time

import mysql.connector
import requests
from bs4 import BeautifulSoup
from contextlib import closing
import re
from fuzzywuzzy import fuzz
from requests import get
from timeit import default_timer as timer

sqlite_connection = None
try:
    sqlite_connection = sqlite3.connect('rustdata.db')
    sqlite_cursor = sqlite_connection.cursor()
except Exception as e:
    print(e)
finally:
    if sqlite_connection:
        print('Successfully connected to SQLite database')


# Gets a BeautifulSoup html object from a given url, and prints out an error if there was an error connecting
# @Param url: URL to scrape
# @Return BS4 object if the scrape was successful. Empty string if unsuccessful
def get_html(url):
    with closing(get(url, stream=True)) as resp:
        content_type = resp.headers['Content-Type'].lower()
        if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
            html = BeautifulSoup(resp.content, 'html.parser')
            return html
        else:
            return ''


# Moves all data from the 'messages' table of the AWS SQL server to the local SQLite file
def migrate_database_messages():
    # Connect to the MySQL server
    with open('serverinfo.txt') as f:
        info = f.read().splitlines()
        f.close()
    cursor = None
    try:
        sql_connection = mysql.connector.connect(
            host=info[0],
            database=info[1],
            user=info[2],
            password=info[3]
        )

        if sql_connection.is_connected():
            sql_cursor = sql_connection.cursor()
            print('Connected to mySQL Server')
    except Exception as e:
        pass

    # Get the data from the messages table and insert it into the SQLite file
    sqlite_cursor = sqlite_connection.cursor()
    sql_cursor.execute("""SELECT * FROM messages;""")
    rows = sql_cursor.fetchall()
    for row in rows:
        sqlite_cursor.execute("""INSERT INTO messages(message_id, channel_id, item_name, starting_price, predicted_price, store_url, item_price, img_link)
                                VALUES(?, ?, ?, ?, ?, ?, ?, ?);""",
                              (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]))
    sqlite_connection.commit()


# Moves all data from the 'skin' table of the AWS SQL server to the local SQLite file
def migrate_database_skins():
    # Connect to the MySQL server
    with open('serverinfo.txt') as f:
        info = f.read().splitlines()
        f.close()
    cursor = None
    try:
        sql_connection = mysql.connector.connect(
            host=info[0],
            database=info[1],
            user=info[2],
            password=info[3]
        )

        if sql_connection.is_connected():
            sql_cursor = sql_connection.cursor()
            print('Connected to mySQL Server')
    except Exception as e:
        pass

    # Create a SQLiter cursor and get all skin data
    sqlite_cursor = sqlite_connection.cursor()
    sql_cursor.execute("""SELECT * FROM skin;""")
    rows = sql_cursor.fetchall()
    # Once we have the data, insert it into the SQLite file
    for row in rows:
        sqlite_cursor.execute("""INSERT INTO skin(skin_name, link, initial_price, release_date, skin_type)
                                VALUES(?, ?, ?, ?, ?);""", (row[0], row[1], row[2], row[3], row[4]))
    sqlite_connection.commit()


# Queries the SQLite database for call time data with the AVG aggregate function. Formats data and adds it to a text
# file
def get_aggregate_call_times():
    # Get avg call time from db entries
    get_command_names = """SELECT DISTINCT command_name FROM command_times ORDER BY execution_time ASC"""
    sqlite_cursor = sqlite_connection.cursor()
    sqlite_cursor.execute(get_command_names)
    names = sqlite_cursor.fetchall()
    # Format and output data to a text file
    with open('commandinfo.txt', 'w') as f:
        for name in names:
            get_avg = """SELECT AVG(execution_time) FROM command_times WHERE command_name = ?"""
            sqlite_cursor.execute(get_avg, name)
            avg = "{:.2f}".format(sqlite_cursor.fetchall()[0][0]) + ' seconds\n'
            temp = [name[0], avg]
            f.write(''.join(word.rjust(20) for word in temp))
    f.close()


# Returns the link of each item we are going to attempt to add to the database
# @Return List of item links
def get_item_names():
    # List of all links we want to scrape
    urls = ['https://rustlabs.com/group=itemlist', 'https://rustlabs.com/group=building-blocks',
            'https://rustlabs.com/group=containers', 'https://rustlabs.com/group=else']
    # test_urls = ['https://rustlabs.com/group=food']
    # Initialize list of item names
    item_urls = []

    for url in urls:
        # Get the first div with the wrap id in the body tag. This is to filter out navbar/sitemap links
        url_html = get_html(url).find('body').find('div', {"id": "wrap"})
        # Get all links from the response and add them to the list
        item_urls.extend('https://www.rustlabs.com' + a['href'] for a in url_html.find_all('a'))
    return item_urls


# Scrapes general item data and inserts it into the item table if it is new
def update_items(item_html, item_url):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text

    # Get the item description
    item_description = item_html.find('p', {'class': 'description'})
    if item_description:
        item_description = item_description.text
    # Get the health of the item if it has that stat
    health_table = item_html.find('table', {"class": "deployable-stats-table"})
    if health_table is None:
        health = None
    else:
        health = health_table.find('tr').find_all('td')[1].text
    # Get stats for despawn time, stack size, etc
    stats_table = item_html.find('table', {"class": "stats-table"})
    # If there is no data set all vars to null
    if stats_table is None:
        item_identifier = None
        stack_size = None
        despawn_time = None
    # If we find data, add it to query
    else:
        stats_data = stats_table.find_all('td')
        try:
            item_identifier = stats_data[1].text
            stack_size = stats_data[3].text
            despawn_time = stats_data[5].text
        # Catch the exception where an item has no stack size row. Simply set the var to null
        except Exception as e:
            item_identifier = stats_data[1].text
            stack_size = None
            despawn_time = stats_data[3].text
    # Get the image of the item we are looking up
    try:
        # There are 2 different identifiers for images. The newer one is called main-icon while there is an
        # older one called screenshot. Try the newer one and if we get an error use the old one
        item_img = 'https://www.' + item_html.find('img', {"class": "main-icon"})['src'][2:]
    except TypeError as e:
        item_img = 'https://www.' + item_html.find('img', {"id": "screenshot"})['src'][2:]
    # If there is no previous data, insert the scraped data into the database
    print('\tUpdating initial item info for ' + item_name)
    sql = '''REPLACE INTO items(item_name, item_identifier, stack_size, despawn_time, item_img, health, url, 
                description)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)'''
    sqlite_cursor.execute(sql, (item_name, item_identifier, stack_size, despawn_time, item_img, health, item_url,
                                item_description))
    sqlite_connection.commit()


# Scrapes specific item stats and inserts them into the item table if it is new
def update_stats(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Get all stats tables in case an item has 2(Consumable and melee stats for example)
    stat_table = item_html.find_all('table', {"class": "info-table"})
    # If there is no stat table, don't insert anything into the database
    if not stat_table:
        return
    else:
        for table in stat_table:
            # Get all rows in the stats table and insert them into the database
            stats_rows = table.find_all('tr')
            for row in stats_rows:
                # If we get an index error, that means the stat is categorical(i.e. Obstucts vision, etc) and doesn't
                # need to be added
                try:
                    data = row.find_all('td')
                    stat_name = data[0].text.strip()
                    stat_value = data[1].text.strip()
                    try:
                        stat_value += (' ' + data[1].find('img')['alt'])
                    except Exception:
                        pass
                    # If there is no previous data, insert the scraped data into the database
                    print('\tUpdating item stats for ' + item_name)
                    sql = '''REPLACE INTO item_stats(item_name, stat_name, stat_value) VALUES(?, ?, ?)'''
                    # Strip text from data to remove newline characters found in some tables
                    sqlite_cursor.execute(sql, (item_name, stat_name, stat_value))
                    sqlite_connection.commit()
                except IndexError as e:
                    pass


# Scrapes item recipe and attempts to update database
def update_recipes(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the craft tab and get all data in the table
    craft_tab = item_html.find('div', {"data-name": "craft"})
    # If there is no crafting tab, don't insert any data into the db
    if not craft_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the first result under the craft tab, which is the item recipe
        craft_row = craft_tab.find('tbody').find('tr')
        output_amount = craft_row.find('img', {"class": "blueprint40"}).find_next_sibling()
        if output_amount is None:
            output_amount = 1
        else:
            output_amount = output_amount.text
            if output_amount == '':
                output_amount = 1
            else:
                output_amount = int(''.join(filter(str.isdigit, output_amount)))
        # Get all resources listed in the row
        craft_resources = craft_row.find('td', {"class": "no-padding"}).find_all('a')
        # Insert each resource and their quantities into the db
        for resource in craft_resources:
            # The resources are displayed as images. Get the alt which contains the resource name
            resource_name = resource.find('img')['alt']
            # Get the span containing the quantity of resource required. Remove the 'x' at the front and delete all
            # newlines/whitespace
            resource_quantity = resource.find('span', {"class": "text-in-icon"}).text.strip()
            # If there is no quantity, set it to 1
            if not resource_quantity:
                resource_quantity = '1'
            # Remove all non-digits from the string
            resource_quantity = int(''.join(filter(str.isdigit, resource_quantity)))
            print('\tUpdating crafting recipe for ' + item_name)
            sql = '''REPLACE INTO craftcalc(item_name, resource_name, resource_quantity, output_amount) 
                    VALUES(?, ?, ?, ?)'''
            sqlite_cursor.execute(sql, (item_name, resource_name, resource_quantity, output_amount))
            sqlite_connection.commit()


# Scrapes item recycle output and attempts to update database
def update_recycle_recipes(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the recycle tab and get all data in the table
    recycle_tab = item_html.find('div', {"data-name": "recycle"})
    # If there is no recycle tab, don't insert any data into the db
    if not recycle_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the first result under the recycle tab, which is the recycle output
        recycle_row = recycle_tab.find('tbody').find('tr')
        # Get all resources listed in the row
        recycle_resources = recycle_row.find('td', {"class": "no-padding"}).find_all('a')
        # Insert each resource and their quantities into the db
        for resource in recycle_resources:
            resource_quantity = None
            resource_chance = None
            # The resources are displayed as images. Get the alt which contains the resource name
            resource_name = resource.find('img')['alt']
            # Get the span containing the quantity/chance of resource required.
            temp_value = resource.find('span', {"class": "text-in-icon"}).text.strip()
            # If there is no quantity, set it to 1
            if not temp_value:
                resource_quantity = '1'
            # If there is no percentage in the temp value, strip all non-digits from the quantity
            elif '%' not in temp_value:
                # Remove all non-digits from the string
                resource_quantity = int(''.join(filter(str.isdigit, temp_value)))
            # If there is a percent sign in the temp value, set resource chance to the value
            else:
                resource_chance = temp_value

            # Insert data into the db. In all instances, quantity/value will be null depending on the resource
            print('\tUpdating recycle output for ' + item_name)
            sql = '''REPLACE INTO recycle(item_name, resource_name, resource_quantity, resource_chance) 
                      VALUES(?, ?, ?, ?)'''
            sqlite_cursor.execute(sql, (item_name, resource_name, resource_quantity, resource_chance))
            sqlite_connection.commit()


# Scrapes item repair data and inserts it into the database
def update_repair_costs(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the repair tab and get all data in the table
    repair_tab = item_html.find('div', {"data-name": "repair"})
    # If there is no repair tab, don't insert any data into the db
    if not repair_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the first result under the repair tab, which is the item recipe
        repair_row = repair_tab.find('tbody').find('tr')
        # Get all resources listed in the row
        cols = repair_row.find_all('td')
        try:
            # Get the 4th and 5th cols and insert them into the repair_data db
            condition_loss = cols[3].text
            blueprint_required = cols[4].text
            sql = '''REPLACE INTO repair_data(item_name, condition_loss, blueprint_required) VALUES(?, ?, ?)'''
            sqlite_cursor.execute(sql, (item_name, condition_loss, blueprint_required))
            sqlite_connection.commit()
        # If there is an index error, then we are collecting data for a building that has no condition/bp values
        # and thus only add their repair costs below
        except IndexError as e:
            print('\tSkipping condition/bp stats for ' + item_name)

        # Get all resources from the repair cost tab and insert them into the repair_cost database
        repair_resources = repair_row.find('td', {"class": "no-padding"}).find_all('a')
        # Insert each resource and their quantities into the db
        for resource in repair_resources:
            # The resources are displayed as images. Get the alt which contains the resource name
            resource_name = resource.find('img')['alt']
            # Get the span containing the quantity of resource required. Remove the 'x' at the front and delete all
            # newlines/whitespace
            resource_quantity = resource.find('span', {"class": "text-in-icon"}).text.strip()
            # If there is no quantity, set it to 1
            if not resource_quantity:
                resource_quantity = '1'
            # Remove all non-digits from the string
            resource_quantity = int(''.join(filter(str.isdigit, resource_quantity)))
            print('\tUpdating repair cost for ' + item_name)
            sql = '''REPLACE INTO repair_cost(item_name, resource_name, resource_quantity) VALUES(?, ?, ?)'''
            sqlite_cursor.execute(sql, (item_name, resource_name, resource_quantity))
            sqlite_connection.commit()


# Scrape item drop tables and insert them into the database
def update_drop_tables(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the loot tab
    loot_tab = item_html.find('div', {"data-name": "loot"})
    # If there is no loot tab, don't insert any data into the db
    if not loot_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the table in the loot tab
        loot_table = loot_tab.find('tbody')
        # Get all rows in the loot table
        loot_sources = loot_table.find_all('tr')
        for source in loot_sources:
            # Split each row into columns and get the container and chance values, then insert into the db
            cols = source.find_all('td')
            crate_name = cols[0].text
            # Remove space between value and percent sign
            percent_chance = cols[3].text.replace(' ', '')
            percent_chance = percent_chance.replace('%', '')
            print('\tUpdating drop tables for ' + item_name)
            sql = '''REPLACE INTO droptable(crate_name, item_name, percent_chance) VALUES(?, ?, ?)'''
            sqlite_cursor.execute(sql, (crate_name, item_name, float(percent_chance)))
            sqlite_connection.commit()


# Scrape item drop tables and insert them into the database
def update_durability(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the durability tab
    durability_tab = item_html.find('div', {"data-name": "destroyed-by"})
    # If there is no durability tab, don't insert any data into the db
    if not durability_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get all tools in the melee/explosive categories
        tool_table = durability_tab.find('tbody')
        tools = tool_table.find_all('tr', attrs={"data-group": "explosive"})
        tools.extend(tool_table.find_all('tr', attrs={"data-group": "melee"}))

        # Add each tool and its data to the database
        for tool in tools:
            # Try to get hard/soft side data. If we get an exception set the variable to null
            try:
                item_side = tool["data-group2"]
            except KeyError:
                item_side = 'both'
            cols = tool.find_all('td')
            tool_name = cols[1]["data-value"]
            tool_quantity = cols[2].text
            tool_time = cols[3].text
            tool_sulfur_cost = cols[5]["data-value"]
            # Null sulfur values are set to the max int for some reason, change that to Null
            if tool_sulfur_cost == "2147483647":
                tool_sulfur_cost = None
            print('\tUpdating durability for ' + item_name)
            sql = '''REPLACE INTO durability
            (item_name, item_side, tool_name, tool_quantity, tool_time, tool_sulfur_cost) VALUES(?, ?, ?, ?, ?, ?)'''
            sqlite_cursor.execute(sql, (item_name, item_side, tool_name, tool_quantity, tool_time,
                                        tool_sulfur_cost))
            sqlite_connection.commit()


# Scrape workbench experiment data and add it to the sql server
def update_experiment_tables():
    for i in range(1, 4):
        # Get the workbench HTML and extract all items listed under the experiment tab
        workbench_html = get_html('https://rustlabs.com/item/work-bench-level-' + str(i) + '#tab=experiment')
        workbench_table = workbench_html.find('div', {"data-name": "experiment"}).find('tbody')
        items = workbench_table.find_all('tr')
        # Add all items found to a list and use it to get a formatted string to display
        for item in items:
            item_name = ' '.join(item.find('a').text.split()[:-1])
            print('\tSetting workbench tier for ' + item_name)
            sql = '''UPDATE items SET workbench_tier = ? WHERE item_name = ?'''
            sqlite_cursor.execute(sql, (str(i), item_name))
            sqlite_connection.commit()


# Scrape fuel consumption data and add it to the db
def update_fuel_consumption(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the fueled-by tab
    fuel_tab = item_html.find('div', {"data-name": "fueled-by"})
    # If there is no fueled-by tab, don't insert any data into the db
    if not fuel_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the table in the fuel tab
        fuel_table = fuel_tab.find('tbody').find('tr')
        cols = fuel_table.find_all('td')
        fuel_name = cols[0].find('img')['alt']
        fuel_consumption = cols[2].text + '/hr'
        print('\tUpdating fuel consumption for ' + item_name)
        sql = '''REPLACE INTO fuel_consumption (item_name, fuel_name, fuel_consumption) VALUES(?, ?, ?)'''
        sqlite_cursor.execute(sql, (item_name, fuel_name, fuel_consumption))
        sqlite_connection.commit()


# Scrapes trade data and adds it to db
def update_trades(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the shopping
    shopping_tab = item_html.find('div', {"data-name": "exchange"})
    # The shopping tabs are named 2 different things. Check both before skipping the item
    if not shopping_tab:
        shopping_tab = item_html.find('div', {"data-name": "shopping"})
    # If there is no shopping tab, don't insert any data into the db
    if not shopping_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the table in the loot tab
        shopping_table = shopping_tab.find('tbody')
        # Get all rows in the loot table
        shopping_sources = shopping_table.find_all('tr')
        for source in shopping_sources:
            # Split each row into columns
            cols = source.find_all('td')
            # The first column contains the shop name. Strip unnecessary text to get only the location and shop name
            shop_name = cols[0].text.split('«')[0].replace(' Shopkeeper:', '').replace(' Vending Machine:', '')
            shop_name += "\"" + cols[0].text.split('«')[1][:-1] + "\""
            # Each img without a class name is the icon of a trade item
            trade_items = cols[1].find_all('img', {"class": ""})
            give_item_name = trade_items[0]['alt']
            give_item_quantity = trade_items[0].parent.find('span', {"class": "text-in-icon"}).text
            # Get the item name and quantity of each trade item
            if not give_item_quantity:
                give_item_quantity = '1'
            give_item_quantity = int(''.join(filter(str.isdigit, give_item_quantity)))
            try:
                receive_item_name = trade_items[1]['alt']
                receive_item_quantity = trade_items[1].parent.find('span', {"class": "text-in-icon"}).text
                # If there is no text-in-icon attribute, set the quantity to 1
                if not receive_item_quantity:
                    receive_item_quantity = '1'
                # Extract only digits from the quantity
                receive_item_quantity = int(''.join(filter(str.isdigit, receive_item_quantity)))
            except IndexError:
                # Try to get the receive item, if there is none then we are trading for a vehicle
                receive_item_name = item_name
                receive_item_quantity = '1'
            print('\tUpdating trade data for ' + item_name)
            sql = '''REPLACE INTO trades 
                    (give_item, give_item_quantity, receive_item, receive_item_quantity, shop_name) 
                    VALUES(?, ?, ?, ?, ?)'''
            sqlite_cursor.execute(sql, (give_item_name, give_item_quantity, receive_item_name, receive_item_quantity,
                                        shop_name))
            sqlite_connection.commit()


# Scrape damage values for a weapon and add them to the db
def update_damage_values(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the damage tab
    damage_tab = item_html.find('div', {"data-name": "damage"})
    # If there is no damage tab, don't insert any data into the db
    if not damage_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the table header, this will be used to lookup stat names
        damage_table_head_cols = damage_tab.find('thead').find_all('th')
        # Get the table in the damage tab
        damage_table = damage_tab.find('tbody').find_all('tr')
        # Get the stats of each ammo in the table
        for ammo in damage_table:
            cols = ammo.find_all('td')
            ammo_name = cols[1]["data-value"]
            # Get all columns after the name and add their stat names and values to the db
            for i in range(len(cols[2:])):
                stat_value = cols[i + 2].text
                stat_name = damage_table_head_cols[i + 1].text
                print('\tUpdating damage values for ' + item_name)
                sql = '''REPLACE INTO damage (weapon_name, ammo_name, stat_name, stat_value) VALUES(?, ?, ?, ?)'''
                sqlite_cursor.execute(sql, (item_name, ammo_name, stat_name, stat_value))
                sqlite_connection.commit()


# Updates table containing compost values
def update_compost_table():
    compost_html = get_html('https://rustlabs.com/item/fertilizer')
    # Get the table containing composting information and retrieve all rows
    compost_table = compost_html.find('div', {"data-name": "fertilizer"}).find('tbody').find_all('tr')
    for row in compost_table:
        cols = row.find_all('td')
        item_name = cols[1]["data-value"]
        compost_amount = float(cols[2]["data-value"])
        print('\tUpdating compost data for ' + item_name)
        sql = '''REPLACE INTO composting (item_name, compost_amount) VALUES(?, ?)'''
        sqlite_cursor.execute(sql, (item_name, compost_amount))
        sqlite_connection.commit()


# Get gather amounts for all tools and insert them into the db
def update_gather_amounts(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the gather tab
    harvest_tab = item_html.find('div', {"data-name": "gather"})
    # If there is no gather tab, don't insert any data into the db
    if not harvest_tab:
        print('Skipping ' + item_name)
        return
    else:
        # Get the table in the gathered tab and retrieve all rows
        harvest_table = harvest_tab.find('tbody').find_all('tr')
        for row in harvest_table:
            # Split each row into columns and get the container and chance values, then insert into the db
            cols = row.find_all('td')
            node_name = cols[0]["data-value"]
            resources = cols[1].find_all('img')
            time = cols[2].text
            # Get all resources in the 2nd column
            for resource in resources:
                resource_name = resource["alt"]
                resource_quantity = resource.parent.find('span', {"class": "text-in-icon"}).text
                if not resource_quantity:
                    resource_quantity = '1'
                # If there is no percentage in the temp value, strip all non-digits from the quantity
                elif '%' not in resource_quantity:
                    # Remove all non-digits from the string
                    resource_quantity = int(''.join(filter(str.isdigit, resource_quantity)))
                print('\tUpdating gather data for ' + item_name)
                sql = '''REPLACE INTO harvesting(item_name, node_name, resource_name, resource_quantity, time)
                        VALUES(?, ?, ?, ?, ?)'''
                sqlite_cursor.execute(sql, (item_name, node_name, resource_name, resource_quantity, time))
                sqlite_connection.commit()



# Gets all recipes for the mixing table and adds them to the database
def update_mixing_recipes(item_html):
    # Get the name of the item we are looking up
    item_name = item_html.find('h1').text
    # Navigate to the mixing tab
    mixing_tab = item_html.find('div', {"data-name": "mixing"})
    # If there is no mixing tab, don't insert any data into the db
    if not mixing_tab:
        print('Skipping ' + item_name)
        return
    else:

        # Get the table in the mixing tab and retrieve all rows
        mixing_table = mixing_tab.find('tbody').find_all('tr')
        for row in mixing_table:
            # Split each row into columns and get the container and chance values, then insert into the db
            cols = row.find_all('td')
            product_name = cols[1]['data-value']
            ingredients = cols[2].find_all('img')
            quantities = cols[2].find_all('span', {'class': 'text-in-icon'})
            # Because mixing recipes can take the same ingredients and quantities, we must put the recipe in 1 row and
            # make the primary key the item name.
            ingredient_names = [None, None, None, None]
            ingredient_quantities = [None, None, None, None]
            for i in range(len(ingredients)):
                ingredient_names[i] = ingredients[i]['alt']
                ingredient_quantities[i] = quantities[i].text
                if ingredient_quantities[i] == '':
                    ingredient_quantities[i] = '1'
                else:
                    ingredient_quantities[i] = int(''.join(filter(str.isdigit, quantities[i].text)))

            mix_time = int(''.join(filter(str.isdigit, cols[3].text)))

            print('\tUpdating mixing data for ' + product_name)
            sql = '''REPLACE INTO mixing (item_name, ingredient_one_name, ingredient_one_quantity, ingredient_two_name, 
            ingredient_two_quantity, ingredient_three_name, ingredient_three_quantity, ingredient_four_name, 
            ingredient_four_quantity, mix_time) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            sqlite_cursor.execute(sql,
                                  (product_name, ingredient_names[0], ingredient_quantities[0], ingredient_names[1],
                                   ingredient_quantities[1], ingredient_names[2], ingredient_quantities[2],
                                   ingredient_names[3], ingredient_quantities[3], mix_time))
            sqlite_connection.commit()


# Write all item names in the db to a text file
def write_item_names():
    # Get all item names
    get_command_names = """SELECT item_name FROM items ORDER BY item_name ASC"""
    sqlite_cursor.execute(get_command_names)
    names = sqlite_cursor.fetchall()
    # Format and output data to a text file
    with open('item_names.txt', 'w') as f:
        for name in names:
            f.write(name[0] + '\n')
    f.close()


def insert_item_images(skin_name, url):
    print('Inserting image for ' + skin_name)
    skin_html = get_html(url)
    if skin_html == '':
        # Circumvent 429 errors with exponential backoff
        print('\n\n429 response, backing off...\n\n')
        sleep_delay = 10
        while skin_html == '':
            print('Waiting ' + str(sleep_delay) + ' seconds...')
            time.sleep(sleep_delay)
            sleep_delay += 10
            skin_html = get_html(url)
        print('\t\tCooldown expired, reconnecting...')
    img_div = skin_html.find('div', {"class": "market_listing_largeimage"})
    if not img_div:
        print('\tSkipping ' + skin_name)
        return
    img_div = img_div.find('img')['src']
    sql = '''UPDATE skin SET skin_img = ? WHERE skin_name = ?'''
    print('Setting img to ' + img_div)
    sqlite_cursor.execute(sql, (img_div, skin_name))
    sqlite_connection.commit()

# Returns the best item in str_list matching search_term. Identical to get_best_match, but this is for SQL rows
# @Param str_list: list of rows for comparison
# @Param search_term: search term entered
# @Return: Best matching element in str_list
def get_string_best_match(str_list, search_term):
    # This could be done with fuzzywuzzy's process.extractOne module, but I could not get it to work with a different
    # scorer than WRatio.
    best_item_match = None
    best_item_match_num = 0
    for str in str_list:
        # Get an average of multiple fuzzywuzzy scorers to get a better match. Note w is not averaged as its score
        # Is the most valued out of the 5 scorers
        r = fuzz.ratio(search_term, str)
        s = fuzz.token_set_ratio(search_term, str)
        p = fuzz.partial_ratio(search_term, str)
        w = fuzz.WRatio(search_term, str)
        srt = fuzz.token_sort_ratio(search_term, str)
        temp_ratio = (r + s + p + srt) / 4 + w

        if temp_ratio > best_item_match_num:
            best_item_match = str
            best_item_match_num = temp_ratio
        else:
            pass
    return best_item_match


def update_database():
    update_start = timer()
    # Get the url of every item we are going to add to the database
    item_links = get_item_names()
    # print(item_links)
    # Updating composting table should only take place once
    # update_compost_table()
    # Update data for each item
    for link in item_links:
        link_html = get_html(link)
        # update_items(link_html, link)
        # update_stats(link_html)
        # update_recipes(link_html)
        # update_recycle_recipes(link_html)
        # update_repair_costs(link_html)
        # update_drop_tables(link_html)
        # update_durability(link_html)
        # update_fuel_consumption(link_html)
        # update_trades(link_html)
        # update_damage_values(link_html)
        update_gather_amounts(link_html)
        # update_mixing_recipes(link_html)
    # update_steam_games()
    # Update experiment tables after potentially deleting rows in the items table
    # update_experiment_tables()
    # Once all items are updated, write all names to a master text file used for string matching
    # write_item_names()
    update_end = timer()
    return ('Update finished in ' + str(update_end - update_start) + 's')

# update_database()
# get_aggregate_call_times()

if __name__ == "__main__":
    pass
