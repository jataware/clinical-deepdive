import asyncio
import logging
import urllib.parse
from logging import Logger

import aiohttp
from tqdm import tqdm

logger: Logger = logging.getLogger(__name__)

SEARCH_XDD_ES = "https://xdd.wisc.edu/sets/covid/api/beta/search_es_objects?query={term}&ignore_bytes=true&page={page}"


async def retry_search_sem(semi, session, url, retries=5):
    async with semi:
        for i in range(retries):
            try:
                async with session.get(url) as response:
                    return await response.json()
            except aiohttp.ClientResponseError:
                asyncio.sleep(10 * i)
                if i == (retries - 1):
                    logger.exception("Max attempts reached")
                    raise


async def search_xdd_es(semi, session, term, co_callback=None):
    quote_term = urllib.parse.quote_plus(term)
    seed_url = SEARCH_XDD_ES.format(term=quote_term, page=0)
    result = await retry_search_sem(semi, session, seed_url)
    pages = result["total_results"] // 10
    urls = [SEARCH_XDD_ES.format(term=quote_term, page=n) for n in range(1, pages + 1)]
    tasks = [retry_search_sem(semi, session, url) for url in urls]

    if co_callback:
        await co_callback(result)

    for f in tqdm(
        asyncio.as_completed(tasks),
        total=len(tasks),
        ncols=100,
        unit_scale=True,
        desc=f"Searching {term} - {pages} pages",
    ):

        result = await f
        if co_callback:
            await co_callback(result)
