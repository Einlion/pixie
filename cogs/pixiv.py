import asyncio
import json
from datetime import datetime

import aiosqlite
import discord
from aiohttp import ClientSession
from discord.ext import commands, tasks
from utils.pixiv_utils import (get_artist_info, get_follows,
                               get_image_metadata, limited_gather)


class Pixiv(commands.Cog):
    def __init__(self, bot):
        async def init_database():
            async with aiosqlite.connect("artists.db") as c:
                await c.execute(
                    """CREATE TABLE IF NOT EXISTS Artists(
                    ID INTEGER NOT NULL PRIMARY KEY,
                    Illusts INTEGER,
                    Manga INTEGER
                )"""
                )
        self.bot = bot
        self.session = ClientSession()
        asyncio.run(init_database())
        with open("config.json") as f:
            data = json.load(f)
            self.watchlist = data["watchlist"]
        self.nconcurrent_requests = 20

    def cancel_schedulers(self):
        try:
            self.updates_scheduler.cancel()
            self.follows_scheduler.cancel()
        except:
            pass

    def start_schedulers(self):
        self.cancel_schedulers()
        self.updates_scheduler.start()
        self.follows_scheduler.start()

    async def cog_check(self, ctx):
        return await ctx.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.cancel_schedulers()
        super().cog_unload()

    @commands.command()
    async def start(self, ctx):
        self.destination = ctx.channel
        self.start_schedulers()
        await ctx.send("Channel successfully set for new updates")

    @commands.command()
    async def stop(self, ctx):
        self.cancel_schedulers()
        await ctx.send("Successfully stopped")

    @tasks.loop(minutes=1)
    async def updates_scheduler(self):
        artists = []
        illust_ids = []
        inserts = []
        async with aiosqlite.connect("artists.db") as c:
            artists = await (await c.execute("SELECT * FROM Artists")).fetchall()
        
        latest_info_packets = await limited_gather(self.nconcurrent_requests, *[get_artist_info(artist[0], self.session) for artist in artists])

        for i in range(len(artists)):
            artist_id, outdated_total_illusts, outdated_total_manga = artists[i]
            latest_info = latest_info_packets[i]
            is_updated = False
            latest_total_illusts = latest_info["total"]["illusts"]
            latest_total_manga = latest_info["total"]["manga"]

            if latest_total_illusts > outdated_total_illusts:
                diff = latest_total_illusts - outdated_total_illusts
                illust_ids.extend(latest_info["illusts"][0:diff])
                is_updated = True

            if latest_total_manga > outdated_total_manga:
                diff = latest_total_manga - outdated_total_manga
                illust_ids.extend(latest_info["manga"][0:diff])
                is_updated = True

            if is_updated:
                inserts.append((latest_total_illusts, latest_total_manga, artist_id))

        async with aiosqlite.connect("artists.db") as c:
            await c.executemany(
                "UPDATE Artists SET Illusts=?, Manga=? WHERE ID=?",
                inserts,
            )
            await c.commit()
        await self.send_illust_helper(self.destination, illust_ids, self.session)

    @tasks.loop(hours=1)
    async def follows_scheduler(self):
        follows = []
        for ID in self.watchlist:
            follows.extend(await get_follows(ID, self.session))
        await self.import_helper(follows)

    @staticmethod
    async def send_illust_helper(channel, illust_ids: list, session):
        for id in illust_ids:
            try:
                metadata = await get_image_metadata(id, session)
                for url in metadata["urls"]:

                    embed = discord.Embed(
                        title=f"Art by {metadata['artist']}",
                        color=0x4285F4,
                        description=metadata["desc"].replace("#", ""),
                    )

                    embed.set_image(url=url)
                    embed.add_field(
                        name=f"\u200b",
                        value=f"[Link](https://www.pixiv.net/artworks/{id})",
                        inline=False,
                    )
                    thumbnail = discord.File("./pixiv.png", filename="pixiv.png")
                    embed.set_author(name="Pixiv", icon_url="attachment://pixiv.png")
                    embed.set_footer(text="Uploaded at")
                    embed.timestamp = datetime.utcfromtimestamp(metadata["timestamp"])
                    await channel.send(file=thumbnail, embed=embed)
            except Exception as e:
                await channel.send(f"https://www.pixiv.net/artworks/{id}")

    @commands.command(name="watch")
    async def add_to_watchlist(self, ctx, ID: int):
        if ID in self.watchlist:
            return await ctx.send("This user is already being watched.")
        message = await ctx.send("Importing follows of user ID: " + str(ID))
        self.set_watchlist([*self.watchlist, ID])
        
        IDs = await limited_gather(self.nconcurrent_requests, *[get_follows(ID, self.session) for ID in self.watchlist])
        await self.import_helper([el for sub_list in IDs for el in sub_list])
        await message.edit(content="Successfully added for watching.")
    
    @commands.command(name="unwatch")
    async def remove_from_watchlist(self, ctx, ID: int):
        if ID in self.watchlist:
            return await ctx.send("This user is not being watched.")
        message = await ctx.send("Deleting follows of user ID: " + str(ID))
        self.set_watchlist([_ID for _ID in self.watchlist if _ID != ID])
        
        IDs = await limited_gather(self.nconcurrent_requests, *[get_follows(ID, self.session) for ID in self.watchlist])
        await self.import_helper([el for sub_list in IDs for el in sub_list])
        await message.edit(content="Successfully unwatched.")
    
    @commands.command(name="total")
    async def get_total_follows(self, ctx):
        if(self.updates_scheduler.is_running()):
            async with aiosqlite.connect("artists.db") as c:
                total = (
                    await (await c.execute("SELECT COUNT(ID) FROM Artists")).fetchone()
                )[0]
                await ctx.send(f"You are currently listening to {total} artists")
        else:
            await ctx.send(f"You are currently listening to 0 artists")

    async def import_helper(self, IDs):
        current_watchlist = []
        async with aiosqlite.connect("artists.db") as c:
            current_watchlist = await (
                await c.execute("SELECT ID from Artists")
            ).fetchall()

        current_watchlist = {artist[0] for artist in current_watchlist}
        new_artists = list(set(IDs) - current_watchlist)
        artist_info_packets = await limited_gather(self.nconcurrent_requests, *[get_artist_info(artist, self.session) for artist in new_artists])

        await self.add_helper(artist_info_packets)
        removed_artists = list(current_watchlist - set(IDs))
        removed_artists = [(ID,) for ID in removed_artists]

        async with aiosqlite.connect("artists.db") as c:
            await c.executemany("DELETE FROM Artists WHERE ID=?", removed_artists)
            await c.commit()

    @staticmethod
    async def add_helper(artist_info_packets: list):
        inserts = []
        for info in artist_info_packets:
            total = info["total"]
            inserts.append((info["ID"], total["illusts"] - 1, total["manga"]))
        async with aiosqlite.connect("artists.db") as c:
            await c.executemany("INSERT OR IGNORE INTO Artists VALUES(?,?,?)", inserts)
            await c.commit()
    
    def set_watchlist(self, IDs):
        self.watchlist = IDs
        with open("config.json", "r+") as f:
            config = json.load(f)
            config["watchlist"] = self.watchlist
            f.seek(0)
            json.dump(config, f)
            f.truncate()

def setup(bot):
    bot.add_cog(Pixiv(bot))
