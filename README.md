Internet Archive backlink adder for Open Library
================================================

This adds `ocaid` and `source_records` values to Open Library editions.

More specifically, it reads a TSV file from [reconcile's](https://github.com/scottbarnes/reconcile/) `report_ia_links_to_ol_but_ol_edition_has_no_ocaid_jsonl`, looks in that TSV for Open Library Edition-Internet Archive OCAID pairs, then sequentially updates each Open Library Edition with the appropriate `ocaid` value if the edition has no `ocaid`. If the script updates the OCAID, it will attempt to update `source_records` as well.

With respect to the TSV, Reconcile will generate it, but it's a TSV the format `OL_EDITION_ID\tOCAID`. E.g.:
```csv
OL12345M  odysseybookiv00home
OL67890M  aliceimspiegella00carrrich
```

## Use with a watch directory
- Edit `ia_ol_backlink_bot/main.py` at line 227/228 to change the `base_url` value as needed to tell `olclient` which host to use.
- Create a `.env` file in the root directory, and add `bot_user` and `bot_password` to it. E.g.:
```bash
bot_user=openlibrary@example.org
bot_password=admin123
```
- The script will just keep processing items, one every .8 seconds until it has no more. This value is configurable in `pyproject.toml` under `ocaid_add_delay`
- Run `docker-compose up` or `docker-compose up -d` from the directory with `docker-compose.yml`. This runs as a daemon and constantly monitors `watch_dir`, and, if running in the foreground, will print to the console information as it processes each item.
- Put a TSV file with olid-ocaid pairs into `watch_dir` and the daemon will read it within 10 seconds and begin processing. Any successive files will be processed in turn.
- Adding duplicate files/items will cause the script to re-check the same editions, so don't add duplicates.
- If the script crashes for some reason, Docker will restart it and it will continue until done.

## Use with POSTing new items to localhost:8082/add
Up until the part about the TSV file, everything here is the same, but rather reading new items from a TSV file of olid-ocaid pairs from `watch_dir`, this reads a POST from /add. This endpoint uses [FastAPI](https://fastapi.tiangolo.com/), and therefore [OpenAPI](https://www.openapis.org/)/Swagger, so see /docs for the schema. That said, a curl request would look like:
```
curl -X 'POST' \
  'http://localhost:8082/add/' \
  -H 'accept: application/json' \
  -H 'access_token: YOUR_PLAIN_TEXT_TOKEN_HERE' \
  -H 'Content-Type: application/json' \
  -d '[
  {
    "edition_id": "OL1234M",
    "ocaid": "1234OCAID",
    "status": 0,
    "id": 0
  }
]'
```

However, /add requires authentication via a key/value of `access_token` and `your_plain_text_token_here`. Visiting /docs will demonstrate how to make such a request. To add the token, simply:

Generate a key from the shell with `openssl rand -hex 32`

Then generate API key hashes in Python with:
```
>>> from passlib.hash import pbkdf2_sha512
>>> pbkdf2_sha512.using(salt_size=0, rounds=1).hash("some_api_key")
'$pbkdf2-sha512$1$$X/qVkwnrvVc9hqrKUoIW2djrqnSI84KLtCCO.h1AobuCLnU8q3MAbRC8cLnakvR9nKT2Ews/SUN8xw5YZ9.xkw'
```

The API keys are unsalted because they're random values with around 165 bits of entropy, created with the suggested `openssl rand -hex 32`

Finally, place the hashes on their own lines, without quotes, in API_KEYS_FILE (`.api_keys` by default; see `pyproject.toml`).

## Access the SQLite database via [Adminer](https://www.adminer.org/)

NOTE: There will not be any content in this database until an appropriate TSV file is put into `watch_dir`.

The status of each item is tracked in an SQLite database to make it easy to query the status of each item, and [Adminer](https://www.adminer.org/) is included in `docker-compose.yml` to make it easier to run queries. However, because of password requirements, some setup is required first.

### Setup

- Create a file named `login-password-less.php` in the root directory and add the following contents:
```php
<?php
require_once('plugins/login-password-less.php');

/** Set allowed password
*   @param string result of password_hash
**/
return new AdminerLoginPasswordLess(
  password_hash("unhashed-password-here", PASSWORD_DEFAULT)
);

```

### Use
- Login via http://localhost:8081/?sqlite=&username=&db=files%2Fsqlite.db. The username does not matter. For "System" select `SQLite3` and for password put your unhashed password. For "Database" enter `files/sqlite.db`.
- For the `status` key, the values are as follows:
  - 0: item needs its `ocaid` updated.
  - 1: item has had its `ocaid` updated by this script.
  - 2: item has had its `ocaid` updated by something else between the time reconcile generated the report and the time this script tried to update the item.
  - 3: there was an error processing this entry.

### Helpful queries in Adminer
To simplify observation of how things are going, it be helpful to click on the "SQL command" link in the left, where the database is entered, and to enter the following query to see the output grouped by status (e.g. 0, 1, 2, or 3):
```sql
SELECT status, COUNT(status)
FROM "link_items"
GROUP BY status
```

# Testing
Regrettably, I didn't mock anything for the tests, so it uses the local development environment. If someone is really motivated and wants to modify this and wishes to use the tests, let me know and I will update the documentation, or better, the tests. :)

To that end, the tests will fail on the default developer environment, as the tests, sadly, try to modify three editions in the local environment, before reverting them, but they will fail when on the default setup. If for some reason they don't fail and do edit things and fail to revert, the editions are:
- OL24173003M (Gulliver's Travels)
- OL13517105M (The German edition of Alice in Wonderland)
- OL13517105M (The Odyssey)
