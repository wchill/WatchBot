import ruamel.yaml
from cytube_bot import CytubeBot
from discord.ext import commands

CONFIG_FILE = 'config.yaml'

with open(CONFIG_FILE, 'r') as f:
    settings = ruamel.yaml.load(f.read(), ruamel.yaml.RoundTripLoader)

DISCORD_CLIENT_KEY = settings['login']['discord_client_key']

STREAM_URL = settings['stream']['stream_url']
RTMP_ENDPOINT = settings['stream']['rtmp_endpoint']
MEDIA_DIRECTORY = settings['stream']['media_directory']
CHANNEL_WHITELIST = settings['channels']['whitelist']

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), description='A bot that plays videos on CyTube')
bot.add_cog(CytubeBot(bot, STREAM_URL, RTMP_ENDPOINT, MEDIA_DIRECTORY, CHANNEL_WHITELIST))
bot.run(DISCORD_CLIENT_KEY)