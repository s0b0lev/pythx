"""This module contains helper functions for config files and Client recovery."""

import json
import sys
from os import environ, path

import click
from pythx.api import Client
from pythx.cli.logger import LOGGER

CONFIG_KEYS = ("access", "refresh", "username", "password")


def parse_config(config_path, tokens_required=False):
    """Recover the user configuration file.

    This file holds their most recent access and refresh JWT tokens. It allows PythX to
    restore the user's login state across executions.

    :param config_path: The configuration file's path
    :param tokens_required: Raise an error if the tokens are required but missing
    :return:
    """
    with open(config_path, "r") as config_f:
        config = json.load(config_f)
    keys_present = all(k in config for k in CONFIG_KEYS)
    if not (type(config) == dict and keys_present):
        click.echo(
            "Malformed config file at {} doesn't contain required keys {}".format(
                config_path, CONFIG_KEYS
            )
        )
        sys.exit(1)
    if tokens_required and not (config["access"] and config["refresh"]):
        click.echo(
            "Malformed config file at {} does not contain access and refresh token".format(
                config_path
            )
        )
        sys.exit(1)
    return config


def update_config(config_path, client):
    """Update the user configuration file with the latest login data.

    The stored data encompasses the API password, the user's Ethereum address, and the
    latest access and refresh tokens.

    :param config_path: The configuration file's path
    :param client: The client instance to get the latest information from
    """
    with open(config_path, "w+") as config_f:
        json.dump(
            {
                "username": client.eth_address,
                "password": client.password,
                "access": client.access_token,
                "refresh": client.refresh_token,
            },
            config_f,
        )


def recover_client(config_path, staging=False, exit_on_missing=False):
    """A simple helper method to recover a client instance based on a user config.

    :param config_path: The configuration file's path
    :param staging: A boolean to denote whether to use staging or not
    :param exit_on_missing: Return if the file is missing
    :return:
    """
    if not path.isfile(config_path):
        if exit_on_missing:
            return None
        # config doesn't exist - assume first use
        eth_address = environ.get("PYTHX_USERNAME") or click.prompt(
            "Please enter your Ethereum address",
            type=click.STRING,
            default="0x0000000000000000000000000000000000000000",
        )
        password = environ.get("PYTHX_PASSWORD") or click.prompt(
            "Please enter your MythX password",
            type=click.STRING,
            hide_input=True,
            default="trial",
        )
        c = Client(eth_address=eth_address, password=password, staging=staging)
        c.login()
        update_config(config_path=config_path, client=c)
    else:
        config = parse_config(config_path, tokens_required=True)
        c = Client(
            eth_address=config["username"],
            password=config["password"],
            access_token=config["access"],
            refresh_token=config["refresh"],
            staging=staging,
        )
    return c


def ps_core(config, staging, number):
    """A helper method to retrieve data from the analysis list endpoint.

    This functionality is used in the :code:`pythx ps`, as well as the :code:`pythx top`
    subcommands.

    :param config: The configuration file's path
    :param staging: Boolean to denote whether to use the MythX staging deployment
    :param number: The number of analyses to retrieve
    :return: The API response as AnalysisList domain model
    """
    c = recover_client(config_path=config, staging=staging)
    if c.eth_address == "0x0000000000000000000000000000000000000000":
        click.echo(
            (
                "This functionality is only available to registered users. "
                "Head over to https://mythx.io/ and register a free account to "
                "list your past analyses. Alternatively, you can look up the "
                "status of a specific job by calling 'pythx status <uuid>'."
            )
        )
        sys.exit(0)
    resp = c.analysis_list()
    # TODO: paginate if too few analyses
    resp.analyses = resp.analyses[: number + 1]
    update_config(config_path=config, client=c)
    return resp


def get_source_location_by_offset(filename, offset):
    """Retrieve the Solidity source file's location based on the source map offset.

    :param filename: The Solidity file to analyze
    :param offset: The source map's offset
    :return: The line and column number
    """
    overall = 0
    line_ctr = 0
    with open(filename) as f:
        for line in f:
            line_ctr += 1
            overall += len(line)
            if overall >= offset:
                return line_ctr, overall - offset
    LOGGER.error(
        "Error finding the source location in {} for offset {}".format(filename, offset)
    )
    sys.exit(1)


def compile_from_source(source_path: str, solc_path: str = None):
    """A simple wrapper around solc to compile Solidity source code.

    :param source_path: The source file's path
    :param solc_path: The path to the solc compiler
    :return: The parsed solc compiler JSON output
    """
    solc_path = spawn.find_executable("solc") if solc_path is None else solc_path
    if solc_path is None:
        # user solc path invalid or no default "solc" command found
        click.echo("Invalid solc path. Please make sure solc is on your PATH.")
        sys.exit(1)
    solc_command = [
        solc_path,
        "--combined-json",
        "ast,bin,bin-runtime,srcmap,srcmap-runtime",
        source_path,
    ]
    output = check_output(solc_command)
    return json.loads(output)
