from discord.ext import commands
from discord import DMChannel
import os
import json

bot = commands.Bot("!")


def reload_helper(reload=False):
    extensions = [
        f"cogs.{extension[:-3]}"
        for extension in os.listdir("cogs")
        if extension.endswith(".py")
    ]
    for extension in extensions:
        try:
            if reload:
                bot.reload_extension(extension)
            else:
                bot.load_extension(extension)
            print(extension[5:])
        except Exception as e:
            print("Failed to load cog:", extension, e)
            raise Exception("Cog Load Exception.")

reload_helper()


@bot.command()
async def reload(ctx):
    try:
        reload_helper(True)
        await ctx.send("Succesfully reloaded.")
    except:
        await ctx.send("Unable to reload.")


@bot.event
async def on_message(message):
    await bot.wait_until_ready()
    if message.author.id == bot.user.id:
        return
    if isinstance(message.channel, DMChannel):
        await message.channel.send("I don't reply in DMs. Hmph!")
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument) or isinstance(
        error, commands.BadArgument
    ):
        await ctx.send("This command takes ``pixiv ID`` as a parameter")
        return
    raise error


token = None
with open("config.json") as f:
    token = json.load(f)["token"]
bot.run(token)
