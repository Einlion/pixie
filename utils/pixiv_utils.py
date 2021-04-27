from io import BytesIO
import os
import json

PHPSESSID = ""
with open("./config.json") as f:
    PHPSESSID = json.load(f)["PHPSESSID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.101 Mobile Safari/537.36"
}

COOKIES = {"PHPSESSID": PHPSESSID}

REFERER_HEADER = {"Referer": "https://www.pixiv.net/"}


async def get_artist_infos(IDs: list, session) -> list:
    artist_infos = []
    for ID in IDs:
        async with session.get(
            f"https://www.pixiv.net/ajax/user/{str(ID)}/profile/all",
            headers=HEADERS,
            cookies=COOKIES,
        ) as r:
            resp = await r.json()
            if r.status != 200 or resp["error"]:
                raise Exception("Fetch Error")
            total = {
                "illusts": len(resp["body"]["illusts"]),
                "manga": len(resp["body"]["manga"]),
            }
            manga = resp["body"]["manga"]
            manga = list(manga.keys()) if len(manga) != 0 else []
            illusts = resp["body"]["illusts"]
            illusts = list(illusts.keys()) if len(illusts) != 0 else []
            artist_infos.append(
                {"ID": ID, "total": total, "illusts": illusts, "manga": manga}
            )
    return artist_infos


async def get_follows(ID: int, session):
    start = 0
    end = 1
    follow_list = []
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
                follow_list.append(int(following["userId"]))
            end = resp["body"]["total"]
            start = start + 100
    return follow_list


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
                    page["url_big"]
                    for page in resp["body"]["illust_details"]["manga_a"]
                ]
            }
        except:
            url = resp["body"]["illust_details"]["url_big"]
            metadata = {
                "urls": [
                    url,
                ]
            }
        metadata["desc"] = resp["body"]["illust_details"]["alt"]
        metadata["artist"] = resp["body"]["illust_details"]["author_details"][
            "user_name"
        ]
        metadata["timestamp"] = resp["body"]["illust_details"]["upload_timestamp"]

    return metadata


async def get_image(url, session):
    async with session.get(url, headers=REFERER_HEADER) as r:
        if r.status != 200:
            raise Exception("Fetch Error")
        img = BytesIO(await r.read())
    return img
