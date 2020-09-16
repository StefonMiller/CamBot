# CamBot
CamBot uses web scraping, machine learning, and sql connectivity to bring users all information on Rust skins and items. Currently, all data for items is scraped from rustlabs.com and inserted into a database on a monthly basis. This ensures that item data is always up to date and quick to access. CamBot also uses machine learning with past skin prices/colors in order to give users access to price data on every skin released and attempt to predict future skin prices. See below for a list of commands and their functions. 

Additionally, CamBot can be used to post announcements for the most recent devblog/skins/news as soon as they are updated. Once a new devblog, item store update, or Rustafied news article is published CamBot will post an update in the Discord server and send out a tweet at https://twitter.com/CamBot4.

CamBot creates custom emojis and roles when joining a server. If your server doesn't have room for the emotes, you don't have to use them however they make the commands look a little nicer. The roles are used for a scrap system that awards users 1 scrap for every 10 minutes they spend in a voice channel. The roles offer no additional permissions. 

CamBot needs certain permissions to work. Be sure to give it all requested permissions when adding it to your server!

[Add CamBot to your server](https://discord.com/oauth2/authorize?client_id=684058359686889483&permissions=1980623984&scope=bot)
<br>

# Skins Commands
Skins commands are used to get information on any skin in Rust.
* **skinlist**
 * The skinlist command is used to get aggregate skin data. For example, you can get the top 10 most expensive skins on the market, or the 10 least profitable skins. It can also be used to get all skins for a certain item
* **skindata**
 * Displays information(release date, initial price, profit) for a given skin
* **rustskins**
 * Displays all skins currently on the Rust item store with a predicted price(1 year from release) based off of the prices of all other skins. CamBot will make an automatic announcement and tweet whenever the item store updates.
<br>

# Item Commmands
Item commands are used for getting information on all items in Rust.

* **craftcalc**
 * The craftcalc command calculates the crafting cost of a given item
* **composting**
 * The composting command retrieves information on how much compost each food item yields.
* **harvesting**
 * The harvesting command retrieves information on how many resources a tool will harvest.
* **trades**
 * The trades command will display all trades available at Bandit Camp and Outpost that contain a given item
* **damage**
 * The damage command outputs the damage(HP, headshot multiplier, aim cone, etc) stats for each ammo type in a given weapon
* **mix**
 * The mix command displays the mixing table recipe for a given item
* **durability**
 * The durability command displays how much time/resources it would take to break a building/deployable
* **experiment**
 * The experiment command outputs what item blueprints you can get from experimenting at a given workbench
* **raidcalc**
 * The raidcalc command calculates how many explosives you would need to raid a base
* **banditcamp**
 * The banditcamp command calculates the odds of a sequence of outcomes at the wheel occurring
* **recycle**
 * The recycle command displays the output of recycling a given item
* **droptable**
 * The droptable command outputs all items that drop from a crate/NPC and the chance for each item
* **lootfrom**
 * The lootfrom command outputs all loot sources that drop a given item
* **stats**
 * The stats command displays all general stats(HP, stack size, etc) for a given item
* **repair**
 * The repair command displays the repair cost for an item/building
* **furnaceratios**
 * The furnaceratios command posts images of the most efficient furnace layouts for both large and small furnaces
* **sulfur**
 * The sulfur command calculates how many explosives you can craft with a given amount of sulfur
<br>

# Info Commands
Info commands are used for general info about CamBot and Rust.
* **binds**
  * The binds command is used to display all of the bindable actions and keys in Rust. There is also the ability to display the most popular binds used by players.
* **steamstats**
  * The steamstats command is used to display current player stats for a given game. It displays current players, the montly average, and the monthly gain/loss for a given game.
* **serverpop**
  * The serverpop command displays the current server population for any of the Rust servers.
* **rustnews**
  * The rustnews command posts the most current Rustafied news article pertaining to the upcoming Rust update. Additionally, CamBot will post these news updates as soon as they are posted and post a tweet.
* **devblog**
  * The devblog command posts the most current devblog from FacePunch's website. CamBot will post devblog updates as soon as they are uploaded(within 60 seconds of publishing) and post a tweet.
* **status**
  * The status command displays the network status of all servers CamBot uses to get information. A bad network status for a given server **does not** mean the bot won't work.
<br>

# Settings Commands
Settings commands are mostly administrative commands used to configure CamBot
* **help**
 * The help command displays all available commands and can be used to get more information on a specific command
* **changeprefix**
 * The changeprefix command is used to change the server prefix to call CamBot commands
* **info**
 * The info command displays CamBot's uptime, connected servers, and a link to add it to your server
* **defaultchannel**
 * The defaultchannel command is used to specify the channel where CamBot should post announcements.
* **addemojis**
 * The addemojis command is used to add all of CamBot's emojis to the server(Optional)
* **removeemojis**
 * The removeemojis command is used to remove all of CamBot's emojis from the server
* **removebot**
 * The removebot command removes all of CamBot's emojis and roles and then removes the bot from the server. **You will have to manually remove the emojis and roles if you don't use this command**
 <br>
 
# Scrap Commands
CamBot comes with a scrap system that members can use to get different roles. The roles give no additional permissions and are more of a status symbol.
* **balance**
 * The balance command is used to get a member's current scrap balance
* **gamble**
 * The gamble command is used to bet your scrap on the Bandit Camp wheel
* **give**
 * The give command is used to give scrap to another member
* **scrapinfo**
 * The scrapinfo command is used to get more detailed information on the scrap system and its roles
