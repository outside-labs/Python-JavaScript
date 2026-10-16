import asyncio
import unittest

import fetch_api

from JavaScript import JSON, Array, FetchError, Headers, Promise, Request, Response, fetch


class CompanionTests(unittest.TestCase):
    def test_fetch_and_promise_are_standalone_identities(self):
        for value in (FetchError, Headers, Promise, Request, Response, fetch):
            self.assertIs(value, getattr(fetch_api, value.__name__))

    def test_runtime_transform_after_response_text(self):
        async def run():
            response = Response('{"names": ["Ada", "Lin"]}')
            value = JSON.parse(await response.text())
            self.assertEqual(list(value.names.map(lambda name: name.toUpperCase())), ["ADA", "LIN"])
            self.assertEqual(await Promise.resolve(value.names.length).then(lambda length: length + 1), 3)
        asyncio.run(run())

    def test_fetch_json_retains_standalone_contract(self):
        value = Response('{"names": ["Ada"]}').json().result(timeout=2)
        self.assertIsInstance(value, fetch_api.JSONObject)
        self.assertIs(type(value.names), list)
        self.assertFalse(Array.isArray(value.names))
