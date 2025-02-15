from flask import redirect, render_template, request, url_for
from datetime import date
from sentry_sdk import capture_exception
from werkzeug.exceptions import HTTPException

from app import app
from app.search.dataone import SolrDirectSearch
from app.search.gleaner import GleanerSearch
from app.search.search import SearchResultSet

BAD_REQUEST_STATUS = 400


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/polder/')
def polder():
    """This is for backward compatibility, because /polder has been sent out to
    a bunch of mailing lists.
    """
    return redirect(url_for('home'))


@app.route('/about/')
def about():
    return render_template('about.html')


def _get_date_from_args(arg_name, kwargs):
    arg_date = kwargs.pop(arg_name, None)
    if arg_date:
        return date.fromisoformat(arg_date)
    else:  # empty strings are also falsy and cause trouble
        return None


def _do_combined_search(template, **kwargs):
    sanitized_kwargs = {}
    sanitized_kwargs['text'] = kwargs.pop('text', None)
    # Human-readable pages start at 1
    sanitized_kwargs['page_number'] = int(kwargs.pop('page', 1))

    # These all need to be date objects
    try:
        sanitized_kwargs['start_min'] = _get_date_from_args(
            'start_min', kwargs)
        sanitized_kwargs['start_max'] = _get_date_from_args(
            'start_max', kwargs)
        sanitized_kwargs['end_min'] = _get_date_from_args('end_min', kwargs)
        sanitized_kwargs['end_max'] = _get_date_from_args('end_max', kwargs)

    except ValueError as ve:  # we got some invalid dates
        return str(ve), BAD_REQUEST_STATUS

    dataone = SolrDirectSearch().combined_search(**sanitized_kwargs)
    gleaner = GleanerSearch(
        endpoint_url=app.config['GLEANER_ENDPOINT_URL']).combined_search(**sanitized_kwargs)

    results = SearchResultSet.collate(dataone, gleaner)

    return render_template(template, result_set=results)


@app.route('/search')
# Redirect to a stand-alone page to display results
def nojs_combined_search():
    return _do_combined_search('search.html', **request.args)


@app.route('/api/search')
def combined_search():
    return _do_combined_search('results.html', **request.args)


@app.errorhandler(Exception)
def handle_exception(e):
    # Record it in Sentry
    capture_exception(e)

    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # now you're handling non-HTTP exceptions only
    return render_template("500_generic.html", e=e), 500
