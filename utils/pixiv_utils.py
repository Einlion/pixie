import json
import asyncio

PHPSESSID = ""
PROXY = ""
with open("./config.json") as f:
    data = json.load(f)
    PHPSESSID = data["PHPSESSID"]
    PROXY = data["referer_proxy"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.101 Mobile Safari/537.36"
}

COOKIES = {"PHPSESSID": PHPSESSID}

REFERER_HEADER = {"Referer": "https://www.pixiv.net/"}

async def get_artist_info(ID, session) -> list:
    async with session.get(
        f"https://www.pixiv.net/ajax/user/{str(ID)}/profile/all",
        headers=HEADERS,
        cookies=COOKIES,
    ) as r:
        resp = await r.json()
        if r.status != 200 or resp["error"]:
            raise Exception("Fetch Error")

        manga = list(resp["body"]["manga"].keys()) if len(resp["body"]["manga"]) != 0 else []
        illusts = list(resp["body"]["illusts"].keys()) if len(resp["body"]["illusts"]) != 0 else []

        total = {
            "illusts": len(resp["body"]["illusts"]),
            "manga": len(resp["body"]["manga"]),
        }
        return {"ID": ID, "total": total, "illusts": illusts, "manga": manga}


async def get_follows(ID: int, session):
    start = 0
    end = 1
    follows = []
    while start <= end:
        async with session.get(
            f"https://www.pixiv.net/ajax/user/{str(ID)}/following?offset={str(start)}&limit=100&rest=show",
            headers=HEADERS,
            cookies=COOKIES,
        ) as r:
            resp = await r.json()
            if r.status != 200 or resp["error"]:
                raise Exception("Fetch Error")
            for following in resp["body"]["users"]:
                follows.append(int(following["userId"]))
            end = resp["body"]["total"]
            start = start + 100
    return follows

async def get_image_metadata(ID: int, session):
    async with session.get(
        f"https://www.pixiv.net/touch/ajax/illust/details?illust_id={ID}",
        headers=HEADERS,
    ) as r:
        resp = await r.json()
        if r.status != 200 or resp["error"]:
            raise Exception("Fetch Error")
        try:
            metadata = {
                "urls": [
                    f'{PROXY}/{page["url_big"]}?host=https://pixiv.net'
                    for page in resp["body"]["illust_details"]["manga_a"]
                ]
            }
        except:
            url = resp["body"]["illust_details"]["url_big"]
            metadata = {
                "urls": [
                    f"{PROXY}/{url}?host=https://pixiv.net",
                ]
            }
        metadata["desc"] = resp["body"]["illust_details"]["alt"]
        metadata["artist"] = resp["body"]["illust_details"]["author_details"][
            "user_name"
        ]
        metadata["timestamp"] = resp["body"]["illust_details"]["upload_timestamp"]

    return metadata

async def limited_gather(n, *aws):
    semaphore = asyncio.Semaphore(n)

    async def perform(aw):
        async with semaphore:
            return await aw
    
    return await asyncio.gather(*[perform(aw) for aw in aws])
