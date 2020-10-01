import argparse
import logging
import logging.config
import os
import sys
from typing import Any, Final

import trafaret as t
import yaml

ENV_LOG_CONFIG: Final = "LOG_CONFIG"


def setup_logging(
    default_path="logging.yaml", default_level=logging.INFO, env_key=ENV_LOG_CONFIG
):

    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, "rt") as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)


def load_settings(path):
    with open(path, "rt") as f:
        return yaml.safe_load(f.read())


app_config = t.Dict(
    {
        t.Key("chunk_size"): t.Int(),
        t.Key("retries"): t.Int(),
        t.Key("spacy_model"): t.String(),
        t.Key("output_file"): t.String(),
        t.Key("search_patterns"): t.List(
            t.Dict(
                {
                    "id": t.String(),
                    "term": t.String(),
                    "pattern_matchers": t.List(t.List(t.Dict({}).allow_extra("*"))),
                }
            )
        ),
    }
)


def get_config() -> Any:
    try:
        parser = argparse.ArgumentParser(add_help=False)
        required = parser.add_argument_group("required arguments")  # noqa: F841
        optional = parser.add_argument_group("optional arguments")

        # Add back help
        optional.add_argument(
            "-h",
            "--help",
            action="help",
            default=argparse.SUPPRESS,
            help="show this help message and exit",
        )

        optional.add_argument(
            "--resources",
            type=str,
            default=os.getenv("APP_RESOURCES", f"{os.getcwd()}/resources"),
            help="Directory for application resources to be loaded",
        )

        optional.add_argument(
            "--config",
            type=str,
            default=os.getenv("APP_CONFIG", "app.yaml"),
            help="App config file name in resources directory",
        )

        optional.add_argument(
            "--logging",
            type=str,
            default=os.getenv("APP_LOGGING", "logging.yaml"),
            help="App logging files name in resources directory",
        )

        options = parser.parse_args()
        settings = load_settings(f"{options.resources}/{options.config}")
        app_config.check(settings)
        setup_logging(f"{options.resources}/{options.logging}")
        return settings

    except Exception:
        parser.print_help(sys.stderr)
        raise
    return None
