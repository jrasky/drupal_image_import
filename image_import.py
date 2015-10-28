#!/usr/bin/env python3
# Copyright (c) 2015 Jerome Rasky
# See LICENSE for copying information
from io import BytesIO
from PIL import Image

import mysql.connector, re, getpass, time, os, requests, sys

# settings
HOST = "localhost"
USER = "root"
DB = "qp_drupal"
PASS = getpass.getpass("MySQL password for user '%s': " % USER)
IMG_RE = re.compile('img[^>]*src="([^"]+)"')
CNT_RE = re.compile('^\s*(\w+)\s*/\s*(\w+)')

# make directories
os.makedirs("files/styles/large/public/field/image", 0o755, True)
os.makedirs("files/styles/medium/public/field/image", 0o755, True)
os.makedirs("files/styles/thumbnail/public/field/image", 0o755, True)
os.makedirs("files/field/image", 0o755, True)
os.makedirs("files/pictures", 0o755, True)

# connect to the database
print("Connecting to database...")
conn = mysql.connector.connect(host=HOST, user=USER, passwd=PASS, db=DB)
cur = conn.cursor()

# lock the file_managed database
print("Locking tables...")
cur.execute("lock table file_managed write, file_usage write, field_data_body write, field_revision_body write, field_data_field_image write, field_revision_field_image write")

# start a transaction
cur.execute("start transaction")

# get all the nodes
cur.execute("select nid, vid, language from node where type='article'")

# iterate over these nodes
for (nid, vid, language) in cur.fetchall():
    print("Processing node %s..." % nid)

    # storage
    found_one = False
    image_number = 0
    new_body = ""
    last_end = 0

    # get body info
    cur.execute("select revision_id, body_value, body_summary, body_format from field_data_body where entity_type='node' and deleted=0 and entity_id=%s and delta=0 and language='%s'" % (nid, language))

    # split up the info
    (revision_id, body_value, body_summary, body_format) = cur.fetchone()

    # increment the revision
    revision_id += 1

    # iterate through matches in the body value
    for match in IMG_RE.finditer(body_value):
        # create a page base fname for the files/pictures copy
        page_fname_base = "node_%s_image_%s" % (nid, image_number)
        # increment the image counter
        image_number += 1
        # holder for img_type
        img_type = None

        # add a picture to the article if it doesn't have one
        if not found_one:
            # first image found is used as the article image
            found_one = True

            # download the image
            print("Downloading %s..." % match.group(1))
            resp = requests.get(match.group(1))

            # try to guess the type of the image from content-type
            if "content-type" in resp.headers:
                mime_match = CNT_RE.search(resp.headers['content-type'])
                if mime_match is not None:
                    img_type = mime_match.group(2)
            if img_type is None:
                img_type = "png"

            # create the filename
            fname = "node_%s_image.%s" % (nid, img_type)

            # load the image into PIL
            print("Loading image...")
            try:
                img = Image.open(BytesIO(resp.content))
            except OSError:
                # ignore this URI
                sys.stderr.write("Image failed: %s\n" % match.group(1))
                continue

            # save the original image
            print("Saving to files/field/image/%s" % fname)
            img.save("files/field/image/%s" % fname)

            print("Saving to files/pictures/%s.%s" % (page_fname_base, img_type))
            img.save("files/pictures/%s.%s" % (page_fname_base, img_type))

            # other entries in the table use the base image file as the filesize, so go
            # with that
            file_size = os.path.getsize("files/pictures/%s.%s" % (page_fname_base, img_type))

            # resize to 480, 220, and 100 pixels and save those
            print("Resizing to fit 480x480 into files/styles/large/public/field/image/%s" % fname)
            copy = img.copy()
            copy.thumbnail((480, 480), Image.ANTIALIAS)
            copy.save("files/styles/large/public/field/image/%s" % fname)

            print("Resizing to fit 220x220 into files/styles/medium/public/field/image/%s" % fname)
            copy = img.copy()
            copy.thumbnail((220, 480), Image.ANTIALIAS)
            copy.save("files/styles/medium/public/field/image/%s" % fname)

            print("Resizing to fit 100x100 into files/styles/thumbnail/public/field/image/%s" % fname)
            copy = img.copy()
            copy.thumbnail((100, 100), Image.ANTIALIAS)
            copy.save("files/styles/thumbnail/public/field/image/%s" % fname)

            # create a file entry
            cur.execute("insert into file_managed (fid, uid, filename, uri, filemime, filesize, status, timestamp) values (0, 1, '%s', 'public://field/image/%s', 'image/%s', %s, 1, UNIX_TIMESTAMP())" % (fname, fname, img_type, file_size))

            # get the created fid
            cur.execute("select LAST_INSERT_ID()")
            (fid,) = cur.fetchone()

            # create field data
            cur.execute("insert into field_data_field_image (entity_type, bundle, deleted, entity_id, revision_id, language, delta, field_image_fid, field_image_alt, field_image_title, field_image_width, field_image_height) values ('node', 'article', 0, %s, 0, '%s', 0, %s, '', '', %s, %s)" % (nid, language, fid, img.size[0], img.size[1]))

            # create revision
            cur.execute("insert into field_revision_field_image (entity_type, bundle, deleted, entity_id, revision_id, language, delta, field_image_fid, field_image_alt, field_image_title, field_image_width, field_image_height) values ('node', 'article', 0, %s, 0, '%s', 0, %s, '', '', %s, %s)" % (nid, language, fid, img.size[0], img.size[1]))

            # create usage data
            cur.execute("insert into file_usage (fid, module, type, id, count) values (%s, 'file', 'node', %s, 1)" % (fid, nid))
        else:
            # download the image
            print("Downloading %s..." % match.group(1))
            resp = requests.get(match.group(1))

            # try to guess the type of the image from content-type
            if "content-type" in resp.headers:
                mime_match = CNT_RE.search(resp.headers['content-type'])
                if mime_match is not None:
                    img_type = mime_match.group(2)
            if img_type is None:
                img_type = "png"

            # create the filename
            fname = "node_%s_image.%s" % (nid, img_type)

            # load the image into PIL
            print("Loading image...")
            try:
                img = Image.open(BytesIO(resp.content))
            except OSError:
                # ignore this URI
                sys.stderr.write("Image failed: %s\n" % match.group(1))
                continue

            # save the image
            print("Saving to files/pictures/%s.%s" % (page_fname_base, img_type))
            img.save("files/pictures/%s.%s" % (page_fname_base, img_type))

        # replace URLs in the page
        new_body += body_value[last_end:match.start(1)]
        # add in new url
        new_body += "/sites/default/files/pictures/%s.%s" % (page_fname_base, img_type)
        # set last end
        last_end = match.end(1)

    # only update body info if we made changes
    if last_end != 0:
        print("Updating body...")

        # add in the rest of the body
        new_body += body_value[last_end:]

        # update the current value
        cur.execute("update field_data_body set body_value=%s, revision_id=%s where entity_type='node' and deleted=0 and entity_id=%s and delta=0 and language=%s", (new_body, revision_id, nid, language))

        # create a new revision
        cur.execute("insert into field_revision_body (entity_type, bundle, deleted, entity_id, revision_id, language, delta, body_value, body_summary, body_format) values ('node', 'article', 0, %s, %s, %s, 0, %s, %s, %s)", (nid, revision_id, language, new_body, body_summary, body_format))

        # create a new node revision
        cur.execute("insert into node_revision (nid, vid, uid, title, log, timestamp, status, comment, promote, sticky) select %s, 0, uid, title, log, UNIX_TIMESTAMP(), status, comment, promote, sticky from node_revision where vid=%s" % (nid, vid))

        # grab the id and timestamp
        cur.execute("select vid, timestamp from node_revision where vid=LAST_INSERT_ID()")

        # unpack the info
        (new_vid, timestamp) = cur.fetchone()

        # update node
        cur.execute("update node set vid=%s, changed=%s where nid=%s" % (new_vid, timestamp, nid))

# commit changes
cur.execute("commit")

# unlock tables
cur.execute("unlock tables")

print("Finished!")
