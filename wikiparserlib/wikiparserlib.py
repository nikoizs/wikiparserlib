#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: wikiparserlib.py
#
# Copyright 2021 Niko Izsak
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#

"""
Main code for wikiparserlib.

.. _Google Python Style Guide:
http://google.github.io/styleguide/pyguide.html

"""

import logging
import json
import os
import shutil
from dataclasses import dataclass
import re
import requests
from bs4 import BeautifulSoup

from .config import (
    WIKIPEDIA_SEARCH_API
)

__author__ = '''Niko Izsak <izsak.niko@gmail.com>'''
__docformat__ = '''google'''
__date__ = '''28-02-2021'''
__copyright__ = '''Copyright 2021, Niko Izsak'''
__credits__ = ["Niko Izsak"]
__license__ = '''MIT'''
__maintainer__ = '''Niko Izsak'''
__email__ = '''<izsak.niko@gmail.com>'''
__status__ = '''Development'''  # "Prototype", "Development", "Production".


# This is the main prefix used for logging
LOGGER_BASENAME = '''wikiparserlib'''
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


@dataclass
class SearchResult:
    """Data class for search results."""

    title: str
    url: str


class LoggerMixin():
    """Logger class to inherit the logger from."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.{self.__class__.__name__}')


class WikipediaSeries(LoggerMixin):
    """Wiki series class."""

    def __init__(self) -> None:
        super().__init__()
        self.search_url = WIKIPEDIA_SEARCH_API
        self.seasons = []
        self.title = None

    def __str__(self):
        return f'series seasons: {self.seasons}'

    @staticmethod
    def _get_query_map(name):
        query_map = {
            'episode_list': f'list of {name} episodes',
            'miniseries': f'{name} miniseries',
            'name': f'{name}'
        }
        return query_map

    @staticmethod
    def _get_match_regex(query_type):
        regex_map = {
            'episode_list': '^List of (?P<result_title>.+) episodes',
            'miniseries': '^(?P<result_title>.+) (miniseries)$'
        }
        return regex_map[query_type]

    def search_by_name(self, name):
        """Search wikipedia for a tv show by name.

        Args:
            name (str): The name of the tv show to search for

        Return:
            List[SearchResults]: A list of search result

        """
        for query_type, query in self._get_query_map(name).items():
            self._logger.debug('Searching for {} with type:{}'.format(name, query_type))
            result = self._search(query)
            if result:
                if len(result) == 1:
                    if query_type != 'episode_list':
                        self._logger.debug('setting title to: {}'.format(result[0].title))
                        self.title = result[0].title
                    else:
                        match = re.match(r'{}'.format(self._get_match_regex(query_type)), result[0].title)
                        if match:
                            self.title = match.group('result_title')
                return result
        return result

    def _search(self, query):
        parameters = {'action': 'opensearch',
                      'format': 'json',
                      'formatversion': '2',
                      'search': query}

        response = requests.get(self.search_url, params=parameters)
        if response.ok:
            return [SearchResult(*args) for args in zip(response.json()[1], response.json()[3])]
        self._logger.error('Request failed with code {} and message {}'.format(response.code, response.text))
        return None

    @staticmethod
    def get_soup_by_url(url):
        """Get a BeautifulSoup object from URL."""
        html_response = requests.get(url)
        soup = BeautifulSoup(html_response.text, 'html.parser')
        return soup

    @staticmethod
    def parse_seasons_from_soup(soup):  # Not used.
        """Parse the season numbers from the first season table."""
        season_list = []
        table = soup.find("table", {"class": "wikitable plainrowheaders"})
        t_headers = table.find_all("th")
        for header in t_headers:
            season = header.find("a")
            if season:
                season_list.append(season.contents[0])
        return season_list

    def parse_seasons_and_episodes_from_soup(self, soup):
        """Parse the season and episode tables from the tv show soup object."""
        season_list = []
        tables = soup.find_all("table", {"class": "wikitable plainrowheaders wikiepisodetable"})
        for table in tables:
            season_header = table.find_previous_sibling('h3')
            season_title = season_header.find("span", {"class": "mw-headline"}).get_text(strip=True)
            season = Season(season_title)
            season.episodes = self.parse_html_table_to_json(table)
            season_list.append(season)
        self.seasons = season_list

    @staticmethod
    def parse_html_table_to_json(table):
        """Parse HTML table and extract headers as keys and rows as values in a dictionary."""
        table_data = [[cell.text.strip('"') for cell in row] for row in table("tr", {"class": "vevent"})]
        table_headers = [cell.text.strip() for cell in table.find("tr")("th", {"scope": "col"})]
        results_list = []
        for row in table_data:
            res_dict = {}
            for idx, item in enumerate(row):
                res_dict[table_headers[idx]] = item
            results_list.append(res_dict)
        return json.dumps(results_list, indent=4)

    def write_to_file_system(self):
        """Write series data to the file system. Create folder tree and write episode data as json."""
        for season in self.seasons:
            self._logger.debug("writing results to file sysytem for season: {}".format(season.number))
            directory = os.path.dirname(f'./results/{self.title}/{season.number}/')
            if os.path.exists(directory):
                self._logger.warning("Season folder already exists {}, overwriting it.".format(directory))
                self.delete_dir_tree(directory)
            os.makedirs(directory)
            with open(f'{directory}/episodes.json', 'w') as episodes_file:
                episodes_file.write(season.episodes)

    def delete_dir_tree(self, dir_path):
        """Delete directory tree."""
        try:
            shutil.rmtree(dir_path)
        except OSError as error:
            self._logger.error("Error: {}:{}".format(dir_path, error.strerror))


class Season:
    """Season class.

    Attributes:
        number (str): the season title (Season number)
        episodes (list): List of episodes in the season.

    """

    def __init__(self, number) -> None:
        super().__init__()
        self.number = number
        self.episodes = []

    def get_episodes_json(self):
        """Get episodes as json."""
        episodes = []
        for episode in self.episodes:
            episodes.append(episode.__dict__)
        return json.dumps(episodes)


class Episode:
    """Episode class.

    Attributes:
        title (str): The episode title
        number (str): The episode number in the season.

    """

    def __init__(self, title, number) -> None:
        super().__init__()
        self.title = title
        self.number = number

    def __str__(self):
        return f'episode:{self.number},  title:{self.title}'
