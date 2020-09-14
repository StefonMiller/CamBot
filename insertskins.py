import mysql.connector
import pyotp
import requests
from contextlib import closing
from bs4 import BeautifulSoup
from requests import get
import time
import imgtest
from datetime import datetime


# Class containing information on each skin
# n - name of the skin
# l - link to the skin's store page
# ip - skin's initial price
# cp - skin's current price
# img - link to skin's image
class Skin:
    # Initialize object from bitskins info
    def __init__(self, name, curr_price):
        self.n = name
        self.l = ''
        self.ip = 0
        self.cp = curr_price
        self.t = ''
        self.rd = ''

    def set_link(self, link):
        self.l = link

    def set_init_price(self, init_price):
        self.ip = init_price

    def set_type(self, type):
        self.t = type

    def set_release_date(self, start_date):
        end_date = datetime.date(datetime.now())
        self.rd = (end_date - start_date).days


# Prevent anything from running when imported
def main():
    pass


if __name__ == "__main__":
    main()


# Convenience method to eliminate boilerplate code used to get html
def get_html(url):
    try:
        with closing(get(url, stream=True)) as resp:
            content_type = resp.headers['Content-Type'].lower()
            if resp.status_code == 200 and content_type is not None and content_type.find('html') > -1:
                html = BeautifulSoup(resp.content, 'html.parser')
                return html
            else:
                print('Page ' + url + ' not found status ' + str(resp.status_code))
                print(resp.headers)
                return -1
    except Exception as e:
        print('Connection failed: ' + str(e))


# Initialize the list of skins with info from BitSkins API. This will populate the items with their names and current
# prices
# @Return: A list of Skin objects
def init_skins():
    # Open the text file containing my bitskins API key and secret
    with open('/skinml/bitskins_keys.txt') as f:
        bit_info = f.read().splitlines()
        api_key = bit_info[0]
        secret = bit_info[1]
        f.close()
    # Connect ot the API and get the skin data as a json
    my_secret = secret
    my_token = pyotp.TOTP(my_secret)
    r = requests.get(
        'https://bitskins.com/api/v1/get_all_item_prices/?api_key=' + api_key + '&code=' + my_token.now() + '&app_id=252490')
    data = r.json()
    # For each item retrieved, create a skin object and add it to our items list. Then, return that list
    item_names = data['prices']
    items = []
    for name in item_names:
        items.append(Skin(name['market_hash_name'], name['price']))

    return items


# Fills out any remaining info for all skins passed in
# @Param items: A list of Skin objects
# @Return: A list of Skin objects with all info filled out
def complete_skins(items):
    # Get the server info from the text file
    with open('/skinml/serverinfo.txt') as f:
        info = f.read().splitlines()
        f.close()

    cursor = None
    # Try to connect to the server
    try:
        connection = mysql.connector.connect(
            host=info[0],
            database=info[1],
            user=info[2],
            password=info[3]
        )

        if connection.is_connected():
            db_Info = connection.get_server_info()
            cursor = connection.cursor()
    except Exception as e:
        return -1
    # For each item in the list, set it's info using data retrieved from the SQL server
    for item in items:
        try:
            sql = "SELECT * FROM skin WHERE skin_name = \"" + item.n + "\""
            cursor.execute(sql)
            data = cursor.fetchall()[0]
            # Theoretically, there should always be a match but if there isn't exit the command and let the user know
            if not data:
                print('Item not found!')
                return -1
            # Once we complete a query, add the resulting data to the skin object
            item.set_link(data[1])
            item.set_init_price(data[2])
            item.set_release_date(data[3])
            item.set_type(data[4])
            print('Successfully inserted ' + item.n)
        except IndexError:
            pass
        except mysql.connector.errors.DatabaseError:
            pass
    # Once we complete filling out the item's data, return the completed list
    return items


# Takes completed list of Skin objects and writes their image data along with price data to the csv file
# @Param items: List of completed list of Skin objects
# @Return: Status code of operation
def write_skin(items):
    # Write csv header
    with open('skindata.csv', "w") as f:
        list_colors = imgtest.get_colors()
        list_colors.append('no match')
        list_colors.append('initial_price')
        list_colors.append('curr_price')
        list_colors.append('days_since_release')
        list_colors.append('skin_type')
        list_colors = ','.join(list_colors)
        f.write(list_colors)
        f.write('\n')
        f.close()

    # count and reattach names
    for item in items:
        if item.l == '' or item.ip == 0:
            print('\t' + item.n + ' has no data, skipping...')
        else:
            try:
                print('Getting image data for ' + item.n)

                # Get the image from the link in the SQL Server
                item_img_html = requests.get(item.l)

                # Attempt to get the image src, if we do it too fast we will get a 429 error and have to wait a little
                if item_img_html.status_code == 429:
                    # Circumvent 429 errors with exponential backoff
                    print('\n\n429 response, backing off...\n\n')
                    sleep_delay = 10
                    while item_img_html.status_code == 429:
                        print('Waiting ' + str(sleep_delay) + ' seconds...')
                        time.sleep(sleep_delay)
                        sleep_delay += 10
                        item_img_html = requests.get(item.l)
                    print('\t\tCooldown expired, reconnecting...')
                # Once we have the item's store html, get the link to the image
                item_img_html = BeautifulSoup(item_img_html.content, 'html.parser')
                item_img = item_img_html.find('div', {"class": "market_listing_largeimage"}).find('img')['src']

                # To load the image, we need to get it's content with requests, which can lead to another 429 response
                img_response = requests.get(item_img)
                if img_response.status_code == 429:
                    # Circumvent 429 errors with exponential backoff
                    print('\n\n429 response, backing off...\n\n')
                    sleep_delay = 10
                    while img_response.status_code == 429:
                        print('Waiting ' + str(sleep_delay) + ' seconds...')
                        time.sleep(sleep_delay)
                        sleep_delay += 10
                        img_response = requests.get(item_img)
                    print('\t\tCooldown expired, reconnecting...')

                count_vals = []
                dominant_colors = imgtest.load_image(img_response)
                for color in dominant_colors:
                    count_vals.append(str(dominant_colors[color]))
                count_vals.append(str(item.ip))
                count_vals.append(str(item.cp))
                count_vals.append(str(item.rd))
                count_vals.append(str(item.t))

                # After we get all of the image data into the list, append the item's type, current price, and
                # initial price and then output it to the csv
                counts = ','.join(count_vals)

                with open('skindata.csv', "a") as f:
                    f.write(counts)
                    f.write('\n')
            except Exception as e:
                print('\tSkipping ' + item.n + '\n' + str(e))
            print('Successfully inserted ' + item.n)
            time.sleep(10)


def insert():
    skins = init_skins()

    final_skins = complete_skins(skins)
    if final_skins == -1:
        print('Error when getting item data from the SQL server')
        return final_skins

    print('Successfully got skin list, writing to file...')
    write_skin(final_skins)
    return 1
