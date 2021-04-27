import discord
from discord.ext import commands, tasks
import aiosqlite
from io import BytesIO
from datetime import datetime
from aiohttp import ClientSession
import json

from utils.pixiv_utils import (
    get_artist_infos,
    get_follows,
    get_image_metadata,
    get_image,
)


class Pixiv(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = False
        self.unload_base = self.cog_unload
        self.session = ClientSession()
        with open("config.json") as f:
            self.watchlist = json.load(f)["watchlist"]

    @commands.Cog.listener()
    async def on_ready(self):
        async with aiosqlite.connect("artists.db") as c:
            await c.execute(
                """CREATE TABLE IF NOT EXISTS Artists(
                ID INTEGER NOT NULL PRIMARY KEY,
                Illusts INTEGER,
                Manga INTEGER
            )"""
            )

    def cog_unload(self):
        if self.active:
            self.refresh_scheduler.cancel()
            self.update_follows_scheduler.cancel()
        self.active = False
        self.unload_base()

    @commands.command()
    @commands.is_owner()
    async def start(self, ctx):
        if not self.active:
            self.destination = ctx.channel
            self.refresh_scheduler.start()
            self.update_follows_scheduler.start()
            self.active = True
        else:
            self.destination = ctx.channel
        await ctx.send("Channel successfully set for new updates")

    @commands.command()
    @commands.is_owner()
    async def stop(self, ctx):
        if self.active:
            self.refresh_scheduler.cancel()
            self.active = False
            await ctx.send("Successfully stopped listening to new artworks.")
        else:
            await ctx.send("You are already not listening to new artworks")

    @tasks.loop(minutes=20)
    async def refresh_scheduler(self):
        artists = []
        async with aiosqlite.connect("artists.db") as c:
            artists = await (await c.execute("SELECT * FROM Artists")).fetchall()
        for artist in artists:
            info = (await get_artist_infos([artist[0]], self.session))[0]
            current_total = info["total"]
            illust_ids = []
            if current_total["illusts"] > artist[1]:
                diff = current_total["illusts"] - artist[1]
                illust_ids.extend(info["illusts"][0:diff])
            if current_total["manga"] > artist[2]:
                diff = current_total["manga"] - artist[2]
                illust_ids.extend(info["manga"][0:diff])
            async with aiosqlite.connect("artists.db") as c:
                await c.execute(
                    "UPDATE Artists SET Illusts=?, Manga=? WHERE ID=?",
                    [current_total["illusts"], current_total["manga"], artist[0]],
                )
                await c.commit()
            await self.send_illust_helper(self.destination, illust_ids, self.session)

    @staticmethod
    async def send_illust_helper(channel, illust_ids: list, session):

        for id in illust_ids:
            try:
                metadata = await get_image_metadata(int(id), session)
                for url in metadata["urls"]:
                    filename = url.split("/")[-1]
                    img = discord.File(await get_image(url, session), filename)

                    embed = discord.Embed(
                        title=f"Art by {metadata['artist']}",
                        color=0x4285F4,
                        description=metadata["desc"].replace("#", ""),
                    )

                    embed.set_image(url=("attachment://" + filename))
                    embed.add_field(
                        name=f"\u200b",
                        value=f"[Link](https://www.pixiv.net/artworks/{id})",
                        inline=False,
                    )
                    thumbnail = discord.File("./pixiv.png", filename="pixiv.png")
                    embed.set_author(name="Pixiv", icon_url="attachment://pixiv.png")
                    embed.set_footer(text="Uploaded at")
                    embed.timestamp = datetime.utcfromtimestamp(metadata["timestamp"])
                    await channel.send(files=[img, thumbnail], embed=embed)
            except Exception as e:
                await channel.send(f"https://www.pixiv.net/artworks/{id}")

    @tasks.loop(hours=1)
    async def update_follows_scheduler(self):
        IDs = []
        follows = []
        for ID in self.watchlist:
            follows.extend(await get_follows(ID, self.session))
        await self.import_helper(follows)

    async def import_helper(self, IDs):
        current_watchlist = []
        async with aiosqlite.connect("artists.db") as c:
            current_watchlist = await (
                await c.execute("SELECT ID from Artists")
            ).fetchall()
        current_watchlist = {artist[0] for artist in current_watchlist}
        new_artists = list(set(IDs) - current_watchlist)
        artist_infos = await get_artist_infos(new_artists, self.session)
        await self.add_helper(artist_infos)
        removed_artists = list(current_watchlist - set(IDs))
        removed_artists = [(ID,) for ID in removed_artists]
        async with aiosqlite.connect("artists.db") as c:
            await c.executemany("DELETE FROM Artists WHERE ID=?", removed_artists)
            await c.commit()

    @staticmethod
    async def add_helper(infos: list):
        inserts = []
        for info in infos:
            total = info["total"]
            inserts.append((info["ID"], total["illusts"] - 1, total["manga"]))
        async with aiosqlite.connect("artists.db") as c:
            await c.executemany("INSERT OR IGNORE INTO Artists VALUES(?,?,?)", inserts)
            await c.commit()

    @commands.command(name="import")
    @commands.is_owner()
    async def import_follows(self, ctx, ID: int):
        message = await ctx.send("Importing follows of user ID: " + str(ID))
        self.watchlist.append(ID)
        with open("config.json", "r+") as f:
            config = json.load(f)
            config["watchlist"] = self.watchlist
            f.seek(0)
            json.dump(config, f)
            f.truncate()
        await message.edit(content="Successfully imported.")

    @commands.command(name="total")
    @commands.is_owner()
    async def get_total_follows(self, ctx):
        total = 0
        async with aiosqlite.connect("artists.db") as c:
            total = (
                await (await c.execute("SELECT COUNT(ID) FROM Artists")).fetchone()
            )[0]
        await ctx.send(f"You are currently listening to {total} artists")


def setup(bot):
    bot.add_cog(Pixiv(bot))
