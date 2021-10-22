#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Statica

Statica is a simple SSG (Static Site Generator) using python 3, jinja2 and a few other modules.

Example:
        $ python statica.py     # The default action is to watch and build
        $ python statica.py -d  # The sub-folder to use, i.e. example.com (required)
        $ python statica.py -c  # Clean the output
        $ python statica.py -b  # Manually build
        $ python statica.py -s  # Run a development server for testing
"""

import argparse
import logging
import os
import sys
import shutil
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
import xml.etree.cElementTree as et
# from md2gemini import md2gemini

import htmlmin
from decouple import Config, RepositoryEnv, Csv
from jinja2 import Environment, PackageLoader
from markdown2 import markdown
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--domain", nargs="?", help="Domain to use")
parser.add_argument("-s", "--server", action='store_true', help="Run development server")
parser.add_argument("-b", "--build", action='store_true', help="Generate site contents")
parser.add_argument("-c", "--clean", action='store_true', help="Clean output dir")
parser.add_argument("-w", "--watch", action='store_true', help="Watch for changes then build")
args = parser.parse_args()

DOTENV_FILE = f"./{args.domain}/.env"
env_config = Config(RepositoryEnv(DOTENV_FILE))

SERVER_HOST = env_config('SERVER_HOST', default="localhost", cast=str)
SERVER_PORT = env_config('SERVER_PORT', default=8000, cast=int)
SRC_FOLDER = env_config('SRC_FOLDER', default="src", cast=str)
OUTPUT_PATH = env_config('OUTPUT_PATH', default="dist", cast=str)
INPUT_PATH = env_config('INPUT_PATH', default="src/content", cast=str)
STATIC_FOLDER = env_config('STATIC_FOLDER', default="src/static", cast=str)
TEMPLATES_FOLDER = env_config('TEMPLATES_FOLDER', default="src/templates", cast=str)
ASSETS_INPUT_PATH = env_config('ASSETS_INPUT_PATH', default="src/assets", cast=str)
ASSETS_OUTPUT_PATH = env_config('ASSETS_OUTPUT_PATH', default="dist/assets", cast=str)
SECTIONS = env_config('SECTIONS', default="", cast=Csv())

logger = logging.getLogger()
root = et.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")


class StaticaChangeHandler(FileSystemEventHandler):
    TIME_DELAY = 3

    def __init__(self, statica):
        self.statica = statica
        self.now = datetime.now()
        self.previous = datetime.now() - timedelta(seconds=self.TIME_DELAY)

    def on_any_event(self, event):
        # if self.now - self.previous > timedelta(seconds=self.TIME_DELAY):
        logger.info("Change detected: %s", event)
        self.previous = self.now
        self.now = datetime.now()
        self.statica.build()
    # else:
    #     self.now = datetime.now()


class Statica():

    def __copy_folder(self, src, dest):
        try:
            shutil.copytree(src, dest)
        except OSError as e:
            print('Directory not copied. Error: %s' % e)

    def __copy_files(self, src, dest):
        try:
            for filename in os.listdir(src):
                filepath = os.path.join(STATIC_FOLDER, filename)
                shutil.copy(os.path.abspath(filepath), os.path.abspath(dest))
        except OSError as e:
            print('Files not copied. Error: %s' % e)

    def __get_compressed_html(self, html):
        return htmlmin.minify(html, remove_empty_space=True, remove_comments=True)

    def __build_content(self, template, input, output, list_template=None):
        unprocessed_items = {}
        # gemini_items = {}
        env = Environment(loader=PackageLoader('statica', TEMPLATES_FOLDER))
        for markdown_post in os.listdir(input):
            file_path = os.path.join(input, markdown_post)

            with open(file_path, 'r', encoding="utf-8") as file:
                contents = file.read()
            # gemini_items[markdown_post] = md2gemini(contents, frontmatter=True)
            unprocessed_items[markdown_post] = markdown(contents, extras=['metadata'])

        unprocessed_items = {
            item: unprocessed_items[item] for item in
            sorted(unprocessed_items,
                   key=lambda post: datetime.strptime(unprocessed_items[post].metadata['date'], '%Y-%m-%d'),
                   reverse=True)
        }

        processed_items = []
        for item in unprocessed_items:
            logger.info(f"Processing: {item}")

            item_metadata = unprocessed_items[item].metadata
            file_name = os.path.splitext(item)[0]

            if item_metadata.get('draft', "") == "true":
                continue

            item_data = {
                "content": unprocessed_items[item],
                "title": item_metadata["title"],
                "date": item_metadata["date"],
                "tags": [x.strip() for x in item_metadata.get("tags", "").split(",")],
                "images": [x.strip() for x in item_metadata.get("images", "").split(",")],
                "thumbnail": item_metadata.get("thumbnail", ""),
                "website": item_metadata.get("website", ""),
                "subtitle": item_metadata.get("subtitle", ""),
                "bannerImage": item_metadata.get("bannerImage", ""),
                "slug": file_name
            }

            url = et.SubElement(root, "url")
            et.SubElement(url, "loc").text = f"https://{args.domain}/{item_data['slug']}"
            et.SubElement(url, "changefreq").text = "monthly"
            et.SubElement(url, "lastmod").text = datetime.today().strftime('%Y-%m-%d')
            processed_items.append(item_data)
            item_content = env.get_template(f"{template}.html").render(item=item_data, datetime=datetime)
            item_file_path = f"{output}/{file_name}/index.html"
            # gemini_file_path = f"{output}/gemini/{file_name}.gmi"

            os.makedirs(os.path.dirname(item_file_path), exist_ok=True)
            # os.makedirs(os.path.dirname(gemini_file_path), exist_ok=True)
            # with open(gemini_file_path, 'w', encoding="utf-8") as file:
            #     file.write(gemini_items[item])
            with open(item_file_path, 'w', encoding="utf-8") as file:
                file.write(self.__get_compressed_html(item_content))

        if list_template:
            list_content_html = env.get_template(f"{list_template}.html").render(items=processed_items,
                                                                                 datetime=datetime)
            list_content_gmi = env.get_template(f"{list_template}.gmi").render(items=processed_items, datetime=datetime)
            with open(f"{output}/index.html", 'w', encoding="utf-8") as file:
                file.write(self.__get_compressed_html(list_content_html))
            with open(f"{output}/index.gmi", 'w', encoding="utf-8") as file:
                file.write(list_content_gmi)
        return processed_items

    def build(self):
        start_time = datetime.now()
        self.clean()
        logger.info('Building site...')
        env = Environment(loader=PackageLoader('statica', TEMPLATES_FOLDER))

        items = {}
        for section in SECTIONS:
            if section == "pages":
                items[section] = self.__build_content("pages",
                                                      f"{INPUT_PATH}/{section}",
                                                      f"{OUTPUT_PATH}")
            else:
                items[section] = self.__build_content(f"{section}_show",
                                                      f"{INPUT_PATH}/{section}",
                                                      f"{OUTPUT_PATH}/{section}",
                                                      f"{section}_list")

        home_content = env.get_template('home.html').render(items=items, splitFile=os.path.splitext, datetime=datetime)
        with open(f"{OUTPUT_PATH}/index.html", 'w') as file:
            file.write(self.__get_compressed_html(home_content))

        with open(f"{OUTPUT_PATH}/sitemap.xml", 'wb') as f:
            tree = et.ElementTree(root)
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>');
            tree.write(f, xml_declaration=False, encoding='utf-8')

        logger.info(f"Build time: {datetime.now() - start_time}")

    def server(self):
        logger.info("Starting server...")
        web_dir = os.path.join(os.path.dirname(__file__), OUTPUT_PATH)
        os.chdir(web_dir)
        server_address = (SERVER_HOST, SERVER_PORT)
        logger.info(f"Server running on http://{SERVER_HOST}:{SERVER_PORT}/")
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()

    def clean(self):
        logger.info("Cleaning...")
        for filename in os.listdir(OUTPUT_PATH):
            filepath = os.path.join(OUTPUT_PATH, filename)
            try:
                shutil.rmtree(filepath)
            except OSError:
                os.remove(filepath)
        self.__copy_folder(ASSETS_INPUT_PATH, ASSETS_OUTPUT_PATH)
        self.__copy_files(STATIC_FOLDER, OUTPUT_PATH)

    def watch(self):
        logger.info("Watching for changes...")
        file_path = os.path.join(os.path.abspath(os.getcwd()), SRC_FOLDER)
        event_handler = StaticaChangeHandler(self)
        my_observer = Observer()
        my_observer.schedule(event_handler, file_path, recursive=True)
        my_observer.start()
        try:
            while True:
                time.sleep(3)
        except KeyboardInterrupt:
            my_observer.stop()
            my_observer.join()


def main(args):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger()
    handler = logging.FileHandler('statica.log')
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    statica = Statica()

    if args.server:
        statica.server()
    elif args.build:
        statica.build()
    elif args.clean:
        statica.clean()
    else:
        statica.build()
        statica.watch()


if __name__ == "__main__":
    main(args)
