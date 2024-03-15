#!/usr/bin/python3.8

import http.client
import os
import random
import sys
import time

from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (IOError, http.client.NotConnected,
  http.client.IncompleteRead, http.client.ImproperConnectionState,
  http.client.CannotSendRequest, http.client.CannotSendHeader,
  http.client.ResponseNotReady, http.client.BadStatusLine)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

CLIENT_SECRETS_FILE = "client_secrets.json"

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

def get_authenticated_service(args):
  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
    scope=YOUTUBE_UPLOAD_SCOPE,
    message=MISSING_CLIENT_SECRETS_MESSAGE)

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
    credentials=credentials)

def initialize_upload(youtube, options):
  tags = None
  if options.keywords:
    tags = options.keywords.split(",")

  body = {
    "id": options.video_id,  # Add the video ID here
    "snippet": {
      "title": options.title,
      "description": options.description,
      "tags": tags,
      "categoryId": options.category,
      "defaultLanguage": "en",
      "defaultAudioLanguage": "en"
    },
    "localizations": {
      "es": {
        "title": options.title_es,
        "description": options.description_es
      },
      "zh-CN": {
        "title": options.title_zh,
        "description": options.description_zh
      }
    }
  }

  update_request = youtube.videos().update(
    part="snippet,localizations",
    body=body
  )

  update_response = update_request.execute()

  print(f"Updated video '{update_response['id']}' with multiple language metadata.")

def resumable_upload(insert_request, youtube, options):
  response = None
  error = None
  retry = 0
  while response is None:
    try:
      print("Uploading file...")
      status, response = insert_request.next_chunk()
      if response is not None:
        if 'id' in response:
          print("Video id '%s' was successfully uploaded." % response['id'])
          options.video_id = response['id']
          initialize_upload(youtube, options)
        else:
          exit("The upload failed with an unexpected response: %s" % response)
    except HttpError as e:
      if e.resp.status in RETRIABLE_STATUS_CODES:
        error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status, e.content)
      else:
        raise
    except RETRIABLE_EXCEPTIONS as e:
      error = "A retriable error occurred: %s" % e

    if error is not None:
      print(error)
      retry += 1
      if retry > MAX_RETRIES:
        exit("No longer attempting to retry.")

      max_sleep = 2 ** retry
      sleep_seconds = random.random() * max_sleep
      print("Sleeping %f seconds and then retrying..." % sleep_seconds)
      time.sleep(sleep_seconds)

if __name__ == '__main__':
  argparser.add_argument("--file", required=True, help="Video file to upload")
  argparser.add_argument("--title", help="Video title", default="Test Title")
  argparser.add_argument("--description", help="Video description", default="Test Description")
  argparser.add_argument("--category", default="22", help="Numeric video category. See https://developers.google.com/youtube/v3/docs/videoCategories/list")
  argparser.add_argument("--keywords", help="Video keywords, comma separated", default="")
  argparser.add_argument("--privacyStatus", choices=VALID_PRIVACY_STATUSES, default=VALID_PRIVACY_STATUSES[0], help="Video privacy status.")
  argparser.add_argument("--title_en", help="English video title", default="")
  argparser.add_argument("--description_en", help="English video description", default="")
  argparser.add_argument("--title_es", help="Spanish video title", default="")
  argparser.add_argument("--description_es", help="Spanish video description", default="")
  argparser.add_argument("--title_zh", help="Chinese video title", default="")
  argparser.add_argument("--description_zh", help="Chinese video description", default="")
  args = argparser.parse_args()

  if not os.path.exists(args.file):
    exit("Please specify a valid file using the --file= parameter.")

  youtube = get_authenticated_service(args)
  try:
    initialize_upload(youtube, args)
  except HttpError as e:
    print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
