import asyncio
import json
import logging
from logging import Logger
from time import perf_counter

import aiofiles
import aiohttp
import spacy
from humanfriendly import format_timespan
from spacy.matcher import Matcher

from . import config
from .search import search_xdd_es
from .utils import deep_get

logger: Logger = logging.getLogger(__name__)


def config_matcher(settings, nlp):
    matcher = Matcher(nlp.vocab)

    for pattern in settings["search_patterns"]:
        matcher.add(pattern["id"], None, *pattern["pattern_matchers"])

    return matcher


async def process_highlight(nlp, matcher, item):
    extracted = []
    for i, hl in enumerate(item["highlight"]):
        doc = nlp(hl)
        if matches := matcher(doc):
            for match_id, start, end in matches:
                string_id = nlp.vocab.strings[match_id]
                span = doc[start:end]
                extracted.append(
                    {"highlight_idx": i, "matched_on": string_id, "match": span.text}
                )

    return extracted


def context_result(f, nlp, matcher):
    async def process_page_result(page):
        objects = page.get("objects")

        for o in objects:
            txt = deep_get(o, "object.content")
            doc = nlp(txt)
            o["extracted"] = [
                {
                    "matched_on": nlp.vocab.strings[match_id],
                    "match": doc[start:end].text,
                }
                for match_id, start, end in matcher(doc)
            ]
            await f.write(json.dumps(o) + "\n")

    return process_page_result


async def run(settings, nlp, matcher):
    terms = [term["term"] for term in settings["search_patterns"]]
    sem = asyncio.Semaphore(value=8)
    timeout = aiohttp.ClientTimeout(total=None)  # disable timeout

    async with aiohttp.ClientSession(
        timeout=timeout, raise_for_status=True
    ) as session, aiofiles.open(settings["output_file"], mode="w+") as o:

        for f in [
            search_xdd_es(
                sem, session, term, co_callback=context_result(o, nlp, matcher)
            )
            for term in terms
        ]:
            await f


def main() -> None:
    settings = config.get_config()
    logging.info("main")
    start = perf_counter()
    nlp = spacy.load(settings["spacy_model"])
    matcher = config_matcher(settings, nlp)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(settings, nlp, matcher))
    finished = perf_counter() - start
    pretty_finished = format_timespan(finished)

    logger.info("Completed in %s", pretty_finished)


if __name__ == "__main__":
    main()
