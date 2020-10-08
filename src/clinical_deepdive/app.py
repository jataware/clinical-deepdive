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
from .utils import deep_get, FastWriteCounter

logger: Logger = logging.getLogger(__name__)


def config_matcher(settings, nlp):
    variable_matcher = Matcher(nlp.vocab)
    disease_matcher = Matcher(nlp.vocab)

    for pattern in settings["variable_patterns"]:
        variable_matcher.add(pattern["id"], None, *pattern["pattern_matchers"])

    for pattern in settings["disease_patterns"]:
        disease_matcher.add(pattern["id"], None, *pattern["pattern_matchers"])


    return variable_matcher, disease_matcher

async def to_rows(m: dict):
    rows = []
    diseases = set([d["matched_on"] for d in deep_get(m, "extracted.diseases", [])])
    url = deep_get(m, "bibjson.link")[0]["url"]
    doi = deep_get(m, "bibjson.identifier")[0]["id"]
    dt = deep_get(m, "bibjson.year")
    for d in diseases:
        variables = deep_get(m, "extracted.variables", [])
        for v in variables:
            rows.append({
                "disease": d,
                "url": url,
                "doi": doi,
                "year": dt,
                "var": v["matched_on"],
                "est": v["n"][0],
                "sent": v["sent"].text,
            })

    return rows

def context_result(counter, f, nlp, variable_matcher, disease_matcher):
    async def process_page_result(page):
        objects = page.get("objects")

        for o in objects:
            txt = deep_get(o, "object.content")
            title =  deep_get(o, "bibjson.title")
            doc = nlp(txt)
            o["extracted"] = {}
            o["extracted"]["variables"] = [
                {
                    "matched_on": nlp.vocab.strings[match_id],
                    "match": doc[start:end].text,
                    "n": [x.text for x in doc[start:end] if x.pos_ == "NUM"],
                    "sent": doc[start:end].sent
                }
                for match_id, start, end in variable_matcher(doc)
            ]
            if o["extracted"]["variables"]:
                o["extracted"]["diseases"] = [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent
                    }
                    for match_id, start, end in disease_matcher(doc)
                ] + [ {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent
                    }
                    for match_id, start, end in disease_matcher(nlp(title))
                ]

                # for d in o["extracted"]["diseases"]:
                #     logger.debug(d)

                counter.increment()
                rows = await to_rows(o)
                for row in rows:
                    await f.write(json.dumps(row) + "\n")
                    #counter.increment()

    return process_page_result


async def run(settings, nlp, variable_matcher, disease_matcher, counter):
    terms = [term for term in settings["search_terms"]]
    sem = asyncio.Semaphore(value=8)
    timeout = aiohttp.ClientTimeout(total=None)  # disable timeout

    async with aiohttp.ClientSession(
        timeout=timeout, raise_for_status=True
    ) as session, aiofiles.open(settings["output_file"], mode="w+") as o:

        for f in [
            search_xdd_es(
                sem, session, term, co_callback=context_result(counter, o, nlp, variable_matcher, disease_matcher)
            )
            for term in terms
        ]:
            await f


def main() -> None:
    settings = config.get_config()
    logging.info("main")
    start = perf_counter()
    counter = FastWriteCounter()
    nlp = spacy.load(settings["spacy_model"])
    variable_matcher, disease_matcher = config_matcher(settings, nlp)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(settings, nlp, variable_matcher, disease_matcher, counter))
    finished = perf_counter() - start
    pretty_finished = format_timespan(finished)

    logger.info("total matches: %s", counter.value)
    logger.info("Completed in %s", pretty_finished)


if __name__ == "__main__":
    main()
