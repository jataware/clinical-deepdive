import asyncio
import json
import logging
from logging import Logger
from time import perf_counter

import aiofiles
import aiohttp
import spacy
from dateparser import parse
from humanfriendly import format_timespan
from spacy.matcher import Matcher

from . import config
from .search import search_xdd, search_xdd_es
from .utils import FastWriteCounter, deep_get

logger: Logger = logging.getLogger(__name__)


class hashabledict(dict):
    def __hash__(self):
        return hash(frozenset(self))


def config_matcher(settings, nlp):
    variable_matcher = Matcher(nlp.vocab)
    disease_matcher = Matcher(nlp.vocab)

    for pattern in settings["variable_patterns"]:
        variable_matcher.add(pattern["id"], None, *pattern["pattern_matchers"])

    for pattern in settings["disease_patterns"]:
        disease_matcher.add(pattern["id"], None, *pattern["pattern_matchers"])

    return variable_matcher, disease_matcher


def try_parse_dt(doi):
    """
    parse 10.1101/2020.03.06.20031955
    """
    dt_str = next(iter(doi.split("/")[1:]), None)
    if dt_str:
        s = next(iter(dt_str.rsplit(".", 1)), "")
        dt = parse(s)
        if dt:
            return str(dt.date())
    return ""


async def to_rows_es(m: dict):
    rows = []
    diseases = set([d["matched_on"] for d in deep_get(m, "extracted.diseases", [])])
    url = deep_get(m, "bibjson.link")[0]["url"]
    doi = deep_get(m, "bibjson.identifier")[0]["id"]
    year = deep_get(m, "bibjson.year", "")
    dt = try_parse_dt(doi)
    for d in diseases:
        variables = deep_get(m, "extracted.variables", [])
        for v in variables:
            o = {
                "disease": d,
                "url": url,
                "doi": doi,
                "year": year,
                "dt": dt,
                "variable": v["matched_on"],
                "estimate": next(iter(v.get("n", [])), ""),
                "sentence": v["sent"].text,
            }

            rows.append(hashabledict(o))

    # dedupe
    return list(set(rows))


def context_result_es(
    csv_output: bool, columns, counter, f, nlp, variable_matcher, disease_matcher
):
    async def process_page_result(page):
        objects = page.get("objects")

        for o in objects:
            txt = deep_get(o, "object.content")
            title = deep_get(o, "bibjson.title")
            doc = nlp(txt)
            o["extracted"] = {}
            o["extracted"]["variables"] = [
                {
                    "matched_on": nlp.vocab.strings[match_id],
                    "match": doc[start:end].text,
                    "n": [x.text for x in doc[start:end] if x.pos_ == "NUM"],
                    "sent": doc[start:end].sent,
                }
                for match_id, start, end in variable_matcher(doc)
            ]
            if o["extracted"]["variables"]:
                o["extracted"]["diseases"] = [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent,
                    }
                    for match_id, start, end in disease_matcher(doc)
                ] + [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent,
                    }
                    for match_id, start, end in disease_matcher(nlp(title))
                ]

                # for d in o["extracted"]["diseases"]:
                #     logger.debug(d)

                counter.increment()
                rows = await to_rows(o)
                if csv_output:
                    for row in rows:
                        await f.write(
                            "\t".join([row.get(k, "") for k in columns]) + "\n"
                        )
                else:
                    for row in rows:
                        logger.debug(row)
                        await f.write(json.dumps(row) + "\n")

    return process_page_result


async def to_rows(m: dict):
    rows = []
    diseases = set([d["matched_on"] for d in deep_get(m, "extracted.diseases", [])])
    url = deep_get(m, "bibjson.link")[0]["url"]
    gddid = deep_get(m, "bibjson._gddid")
    doi = deep_get(m, "bibjson.identifier")[0]["id"]
    year = deep_get(m, "bibjson.year", "")
    dt = try_parse_dt(doi)
    for d in diseases:
        variables = deep_get(m, "extracted.variables", [])
        for v in variables:
            o = {
                "disease": d,
                "gddid": gddid,
                "url": url,
                "doi": doi,
                "year": year,
                "dt": dt,
                "variable": v["matched_on"],
                "estimate": next(iter(v.get("n", [])), ""),
                "sentence": v["sent"].text,
            }

            rows.append(hashabledict(o))


    dedupe = list(set(rows))
    return dedupe


def context_result(
    csv_output: bool, columns, counter, f, nlp, variable_matcher, disease_matcher
):
    async def process_page_result(page):
        objects = page.get("objects")
        for o in objects:

            content = deep_get(o, "context_content", "")
            summary = deep_get(o, "context_summary", "")

            keywords = deep_get(o, "context_keywords", "")
            title = deep_get(o, "bibjson.title", "")
            journal = deep_get(o, "bibjson.journal", "")

            children_text = [child.get("content", "") for child in o.get("children", [])]

            o["extracted"] = {}
            o["extracted"]["variables"] = []
            o["extracted"]["diseases"] = []

            for txt in [content, summary, *children_text]:
                if not txt:
                    continue

                doc = nlp(txt)
                o["extracted"]["variables"] += [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "n": [x.text for x in doc[start:end] if x.pos_ == "NUM"],
                        "sent": doc[start:end].sent,
                    }
                    for match_id, start, end in variable_matcher(doc)
                ]

                o["extracted"]["diseases"] += [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent,
                    }
                    for match_id, start, end in disease_matcher(doc)
                ] + [
                    {
                        "matched_on": nlp.vocab.strings[match_id],
                        "match": doc[start:end].text,
                        "sent": doc[start:end].sent,
                    }
                    for match_id, start, end in disease_matcher(nlp(title))
                ]

                # for d in o["extracted"]["diseases"]:
                #     logger.debug(d)

            if o["extracted"]["variables"] and o["extracted"]["diseases"]:
                rows = await to_rows(o)
                if csv_output:
                    for row in rows:
                        await f.write(
                            "\t".join([row.get(k, "") for k in columns]) + "\n"
                        )
                else:
                    for row in rows:
                        await f.write(json.dumps(row) + "\n")

    return process_page_result


async def run(settings, nlp, variable_matcher, disease_matcher, counter):
    terms = [term for term in settings["search_terms"]]
    sem = asyncio.Semaphore(value=8)
    timeout = aiohttp.ClientTimeout(total=None)  # disable timeout

    async with aiohttp.ClientSession(
        timeout=timeout, raise_for_status=True
    ) as session, aiofiles.open(settings["output_file"], mode="w+") as o:
        header = [
            "disease",
            "gddid",
            "url",
            "doi",
            "year",
            "dt",
            "variable",
            "estimate",
            "sentence",
        ]

        if settings["csv"]:
            await o.write("\t".join(header) + "\n")
        for f in [search_xdd(sem, session, term, co_callback=context_result(
                    settings["csv"],
                    header,
                    counter,
                    o,
                    nlp,
                    variable_matcher,
                    disease_matcher,
                ),
            )
            for term in terms
        ]:
            await f

        # if settings["csv"]:
        #     await o.write("\t".join(header) + "\n")
        # for f in [
        #     search_xdd_es(
        #         sem,
        #         session,
        #         term,
        #         co_callback=context_result_es(
        #             settings["csv"],
        #             header,
        #             counter,
        #             o,
        #             nlp,
        #             variable_matcher,
        #             disease_matcher,
        #         ),
        #     )
        #     for term in terms
        # ]:
        #     await f


def main() -> None:
    settings = config.get_config()
    logging.info("main")
    start = perf_counter()
    counter = FastWriteCounter()
    nlp = spacy.load(settings["spacy_model"])
    variable_matcher, disease_matcher = config_matcher(settings, nlp)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        run(settings, nlp, variable_matcher, disease_matcher, counter)
    )
    finished = perf_counter() - start
    pretty_finished = format_timespan(finished)

    logger.info("total matches: %s", counter.value)
    logger.info("Completed in %s", pretty_finished)


if __name__ == "__main__":
    main()
