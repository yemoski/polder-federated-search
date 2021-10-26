import unittest
from unittest.mock import patch, mock_open, Mock
import json
import re
import requests
import requests_mock
from SPARQLWrapper import SPARQLExceptions
from urllib.error import HTTPError
from urllib.parse import unquote
from urllib.response import addinfourl

from app.search import dataone, gleaner, search

test_response = json.loads(
    '{"response": {"numFound": 1, "start": 5, "maxScore": 0.0, "docs": [{"some": "result"}, {"another": "result"}]}}')


class TestSolrDirectSearch(unittest.TestCase):
    def setUp(self):
        self.search = dataone.SolrDirectSearch()

    @requests_mock.Mocker()
    def test_text_search(self, m):
        m.get(
            dataone.SolrDirectSearch.ENDPOINT_URL,
            json=test_response
        )
        expected = search.SearchResultSet(
            total_results=1,
            page_start=5,
            results=test_response['response']['docs']
        )
        results = self.search.text_search(q='test')
        self.assertEqual(results, expected)

        # Did we make the query we expected?
        solr_url = m.request_history[0].url
        self.assertIn('?q=test', solr_url)

        # Did we add the latitude filter?
        self.assertIn(
            f'&fq={dataone.SolrDirectSearch.LATITUDE_FILTER}',
            unquote(solr_url)
        )

    @requests_mock.Mocker()
    def test_search_error(self, m):
        m.get(
            dataone.SolrDirectSearch.ENDPOINT_URL,
            status_code=500
        )
        with self.assertRaises(requests.exceptions.HTTPError):
            results = self.search.text_search(q='test')

    @requests_mock.Mocker()
    def test_missing_kwargs(self, m):
        m.get(
            dataone.SolrDirectSearch.ENDPOINT_URL,
            json=test_response
        )
        results = self.search.text_search()
        self.assertIn(
            f'&fq={dataone.SolrDirectSearch.LATITUDE_FILTER}',
            unquote(m.request_history[0].url)
        )


class TestGleanerSearch(unittest.TestCase):
    def setUp(self):
        self.search = gleaner.GleanerSearch()

    @patch('SPARQLWrapper.SPARQLWrapper.query')
    def test_text_search(self, query):

        # Set up our mock SPARQLWrapper results. We have mocked out the query() method from
        # SPARQLWrapper, but that method returns an object that we immediately call convert() on,
        # and the results of that are what we work with.
        mock_convert = Mock(return_value={"results": {
            "bindings": [
                {
                    's': {'type': 'bnode', 'value': 'thing1'},
                    'score': {'datatype': 'http://www.w3.org/2001/XMLSchema#double', 'type': 'literal', 'value': '0.01953125'},
                    'description': {'type': 'literal', 'value': "Here is a thing"},
                    'name': {'type': 'literal', 'value': 'thing'}
                },
                {
                    's': {'type': 'bnode', 'value': 'thing2'},
                    'score': {'datatype': 'http://www.w3.org/2001/XMLSchema#double', 'type': 'literal', 'value': '0.01953124'},
                    'description': {'type': 'literal', 'value': "Here is a less relevant thing"},
                    'name': {'type': 'literal', 'value': 'thing the second'}
                }
            ]
        }})
        mock_query = Mock()
        mock_query.convert = mock_convert
        query.return_value = mock_query

        # Do the actual test
        expected = search.SearchResultSet(
            total_results=2,
            page_start=0,
            results=[{'s': 'thing1', 'score': '0.01953125', 'description': 'Here is a thing', 'name': 'thing'}, {
                's': 'thing2', 'score': '0.01953124', 'description': 'Here is a less relevant thing', 'name': 'thing the second'}]

        )
        results = self.search.text_search(q='test')
        self.assertEqual(results, expected)

    # gross, but requests-mock does not touch the requests
    # that SPARQLWrapper makes using good old urllib
    # for some reason, even if I try to capture
    # every request, so here we are creating fake file handles
    # because that's what the response object that
    # SPARQLWrapper knows how to work with expects
    @patch('SPARQLWrapper.Wrapper.urlopener')
    def test_search_error(self, urlopen):
        with patch("builtins.open", mock_open(read_data="some data")) as file_patch:
            test_response_fp = open("foo")

        resp = addinfourl(
            test_response_fp,  # our fake file pointer
            {},  # empty headers
            self.search.ENDPOINT_URL
        )
        resp.code = 500
        urlopen.return_value = resp
        urlopen.side_effect = HTTPError(
            "oh no", 500, {}, {}, test_response_fp
        )
        with self.assertRaises(SPARQLExceptions.EndPointInternalError):
            results = self.search.text_search(q='test')


class TestSearchResultSet(unittest.TestCase):
    def test_equal(self):
        results = ['a', 'b', 'c']

        a = search.SearchResultSet(
            total_results=42, page_start=9, results=results)
        b = search.SearchResultSet(
            total_results=42, page_start=9, results=results)
        c = search.SearchResultSet(
            total_results=3, page_start=9, results=results)
        d = search.SearchResultSet(
            total_results=42, page_start=0, results=results)
        e = search.SearchResultSet(
            total_results=42, page_start=9, results=['d', 'e', 'f'])

        self.assertEqual(a, b)
        self.assertEqual(a, a)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)
        self.assertNotEqual(a, e)
        self.assertNotEqual(c, b)

    def test_collate(self):
        results_a = [{'thing': 'a', 'score': 3}, {'thing': 'b', 'score': 1}]
        results_b = [{'thing': 'c', 'score': 2}, {'thing': 'd', 'score': 0}]

        a = search.SearchResultSet(
            total_results=2, page_start=3, results=results_a)
        b = search.SearchResultSet(
            total_results=2, page_start=0, results=results_b)

        c = search.SearchResultSet.collate(a, b)

        expected = search.SearchResultSet(
            total_results=4,
            page_start=0,
            results=[
                {'thing': 'a', 'score': 3},
                {'thing': 'c', 'score': 2},
                {'thing': 'b', 'score': 1},
                {'thing': 'd', 'score': 0}])

        self.assertEqual(c, expected)
