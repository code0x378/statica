#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statica

Statica is a simple SSG (Static Site Generator) using python 3, jinja2 and a few other modules.

Example:
        $ python statica.py     # The default action is to watch and build
        $ python statica.py -c  # Clean the output
        $ python statica.py -b  # Manually build
        $ python statica.py -r  # Run a development server for testing
"""

import argparse
import logging
import os
import shutil
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

from jinja2 import Environment, PackageLoader
from markdown2 import markdown
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import settings

#
# Logging
#
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.FileHandler('statica.log')
handler.setLevel(logging.INFO)
logger.addHandler(handler)

#
# Command Line Args
#
parser = argparse.ArgumentParser()
parser.add_argument("-r", "--run", action='store_true', help="Run development server")
parser.add_argument("-b", "--build", action='store_true', help="Generate site contents")
parser.add_argument("-c", "--clean", action='store_true', help="Clean output dir")
parser.add_argument("-w", "--watch", action='store_true', help="Watch for changes then build")
args = parser.parse_args()


class StaticaChangeHandler(FileSystemEventHandler):

    def __init__(self, statica):
        self.statica = statica

    def on_any_event(self, event):
        logger.info(f"Change detected")
        statica.build()


class Statica():

    def __copy_folder(self, src, dest):
        try:
            shutil.copytree(src, dest)
        except OSError as e:
            print('Directory not copied. Error: %s' % e)

    def __copy_files(self, src, dest):
        try:
            for filename in os.listdir(src):
                filepath = os.path.join(settings.STATIC_FOLDER, filename)
                shutil.copy(os.path.abspath(filepath), os.path.abspath(dest))
        except OSError as e:
            print('Files not copied. Error: %s' % e)

    def __build_content(self, template, input, output, list_template=None):
        unprocessed_items = {}
        for markdown_post in os.listdir(input):
            file_path = os.path.join(input, markdown_post)

            with open(file_path, 'r', encoding="utf8", errors='ignore') as file:
                unprocessed_items[markdown_post] = markdown(file.read(), extras=['metadata'])

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
                'content': unprocessed_items[item],
                'title': item_metadata['title'],
                'date': item_metadata['date'],
                'tags': item_metadata.get('tags', "").strip().split(','),
                'slug': file_name
            }

            processed_items.append(item_data)
            post_html = template.render(item=item_data)
            post_file_path = f"{output}/{file_name}.html"

            os.makedirs(os.path.dirname(post_file_path), exist_ok=True)
            with open(post_file_path, 'w') as file:
                file.write(post_html)

        if list_template:
            list_content = list_template.render(items=processed_items)
            with open(f"{output}/index.html", 'w') as file:
                file.write(list_content)

        return processed_items

    def build(self):
        self.clean()
        logger.info('Building site...')

        env = Environment(loader=PackageLoader('statica', settings.TEMPLATES_FOLDER))
        #
        # Build sections (i.e. blog, news, events, etc)
        #
        items = {}
        for section in settings.SECTIONS:
            if section == "pages":
                items[section] = self.__build_content(env.get_template('pages.html'),
                                                      f"{settings.INPUT_PATH}/{section}",
                                                      f"{settings.OUTPUT_PATH}")
            else:
                items[section] = self.__build_content(env.get_template(f"{section}_show.html"),
                                                      f"{settings.INPUT_PATH}/{section}",
                                                      f"{settings.OUTPUT_PATH}/{section}",
                                                      env.get_template(f"{section}_list.html"))
        #
        # Homepage Index
        #
        home_html = env.get_template('home.html').render(items=items, splitFile=os.path.splitext)

        with open(f"{settings.OUTPUT_PATH}/index.html", 'w') as file:
            file.write(home_html)

    def run(self):
        logger.info("Starting server...")
        web_dir = os.path.join(os.path.dirname(__file__), settings.OUTPUT_PATH)
        os.chdir(web_dir)
        server_address = (settings.SERVER_HOST, settings.SERVER_PORT)
        logger.info(f"Server running on http://{settings.SERVER_HOST}:{settings.SERVER_PORT}/")
        httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
        httpd.serve_forever()

    def clean(self):
        logger.info("Cleaning...")
        for filename in os.listdir(settings.OUTPUT_PATH):
            filepath = os.path.join(settings.OUTPUT_PATH, filename)
            try:
                shutil.rmtree(filepath)
            except OSError:
                os.remove(filepath)
        self.__copy_folder(settings.ASSETS_INPUT_PATH, settings.ASSETS_OUTPUT_PATH)
        self.__copy_files(settings.STATIC_FOLDER, settings.OUTPUT_PATH)

    def watch(self):
        logger.info("Watching for changes...")
        file_path = os.path.join(os.path.abspath(os.getcwd()), settings.SRC_FOLDER)
        event_handler = StaticaChangeHandler(self)
        my_observer = Observer()
        my_observer.schedule(event_handler, file_path, recursive=True)
        my_observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            my_observer.stop()
            my_observer.join()


if __name__ == "__main__":

    statica = Statica()

    if args.run:
        statica.run()
    elif args.build:
        statica.build()
    elif args.clean:
        statica.clean()
    else:
        statica.build()
        statica.watch()
