from __future__ import absolute_import

import operator
from collections import Mapping
from functools import wraps, partial
from types import MethodType

from flask import make_response as original_flask_make_response
from flask import request, url_for, current_app
from flask.helpers import _endpoint_from_view_func
from flask.views import MethodView
from werkzeug.exceptions import NotAcceptable, InternalServerError
from werkzeug.wrappers import Response as ResponseBase

from flask_rips.representations.json import output_json
from flask_rips.utils import http_status_message, unpack, OrderedDict

__all__ = ('Api', 'Resource')

DEFAULT_REPRESENTATIONS = [('application/json', output_json)]


class Api(object):
    """
    The main entry point for the application.
    You need to initialize it with a Flask Application: ::

    >>> app = Flask(__name__)
    >>> api = restful.Api(app)

    Alternatively, you can use :meth:`init_app` to set the Flask application
    after it has been constructed.

    :param app: the Flask application object
    :type app: flask.Flask or flask.Blueprint
    :param prefix: Prefix all routes with a value, eg v1 or 2010-04-01
    :type prefix: str
    :param default_mediatype: The default media type to return
    :type default_mediatype: str
    :param decorators: Decorators to attach to every resource
    :type decorators: list
    :param catch_all_404s: Use :meth:`handle_error`
        to handle 404 errors throughout your app
    :param serve_challenge_on_401: Whether to serve a challenge response to
        clients on receiving 401. This usually leads to a username/password
        popup in web browsers.
    :param url_part_order: A string that controls the order that the pieces
        of the url are concatenated when the full url is constructed.  'b'
        is the blueprint (or blueprint registration) prefix, 'a' is the api
        prefix, and 'e' is the path component the endpoint is added with
    :type catch_all_404s: bool
    :param errors: A dictionary to define a custom response for each
        exception or error raised during a request
    :type errors: dict

    """

    def __init__(self, app=None, prefix='',
                 default_mediatype='application/json', decorators=None,
                 catch_all_404s=False, serve_challenge_on_401=False,
                 url_part_order='bae', errors=None):
        self.representations = OrderedDict(DEFAULT_REPRESENTATIONS)
        self.urls = {}
        self.prefix = prefix
        self.default_mediatype = default_mediatype
        self.decorators = decorators if decorators else []
        self.catch_all_404s = catch_all_404s
        self.serve_challenge_on_401 = serve_challenge_on_401
        self.url_part_order = url_part_order
        self.errors = errors or {}
        self.blueprint_setup = None
        self.endpoints = set()
        self.resources = []
        self.app = None
        self.blueprint = None

        if app is not None:
            self.app = app
            self.init_app(app)

    def init_app(self, app):
        """Initialize this class with the given :class:`flask.Flask`
        application or :class:`flask.Blueprint` object.

        :param app: the Flask application or blueprint object
        :type app: flask.Flask
        :type app: flask.Blueprint

        Examples::

            api = Api()
            api.add_resource(...)
            api.init_app(app)

        """
        # If app is a blueprint, defer the initialization
        try:
            app.record(self._deferred_blueprint_init)
        # Flask.Blueprint has a 'record' attribute, Flask.Api does not
        except AttributeError:
            self._init_app(app)
        else:
            self.blueprint = app

    def _complete_url(self, url_part, registration_prefix):
        """This method is used to defer the construction of the final url in
        the case that the Api is created with a Blueprint.

        :param url_part: The part of the url the endpoint is registered with
        :param registration_prefix: The part of the url contributed by the
            blueprint.  Generally speaking, BlueprintSetupState.url_prefix
        """
        parts = {
            'b': registration_prefix,
            'a': self.prefix,
            'e': url_part
        }
        return ''.join(parts[key] for key in self.url_part_order if parts[key])

    @staticmethod
    def _blueprint_setup_add_url_rule_patch(blueprint_setup, rule, endpoint=None, view_func=None, **options):
        """Method used to patch BlueprintSetupState.add_url_rule for setup
        state instance corresponding to this Api instance.  Exists primarily
        to enable _complete_url's function.

        :param blueprint_setup: The BlueprintSetupState instance (self)
        :param rule: A string or callable that takes a string and returns a
            string(_complete_url) that is the url rule for the endpoint
            being registered
        :param endpoint: See BlueprintSetupState.add_url_rule
        :param view_func: See BlueprintSetupState.add_url_rule
        :param **options: See BlueprintSetupState.add_url_rule
        """

        if callable(rule):
            rule = rule(blueprint_setup.url_prefix)
        elif blueprint_setup.url_prefix:
            rule = blueprint_setup.url_prefix + rule
        options.setdefault('subdomain', blueprint_setup.subdomain)
        if endpoint is None:
            endpoint = _endpoint_from_view_func(view_func)
        defaults = blueprint_setup.url_defaults
        if 'defaults' in options:
            defaults = dict(defaults, **options.pop('defaults'))
        blueprint_setup.app.add_url_rule(rule, '%s.%s' % (blueprint_setup.blueprint.name, endpoint),
                                         view_func, defaults=defaults, **options)

    def _deferred_blueprint_init(self, setup_state):
        """Synchronize prefix between blueprint/api and registration options, then
        perform initialization with setup_state.app :class:`flask.Flask` object.
        When a :class:`flask_rips.Api` object is initialized with a blueprint,
        this method is recorded on the blueprint to be run when the blueprint is later
        registered to a :class:`flask.Flask` object.  This method also monkeypatches
        BlueprintSetupState.add_url_rule with _blueprint_setup_add_url_rule_patch.

        :param setup_state: The setup state object passed to deferred functions
            during blueprint registration
        :type setup_state: flask.blueprints.BlueprintSetupState

        """

        self.blueprint_setup = setup_state
        if setup_state.add_url_rule.__name__ != '_blueprint_setup_add_url_rule_patch':
            setup_state._original_add_url_rule = setup_state.add_url_rule
            setup_state.add_url_rule = MethodType(Api._blueprint_setup_add_url_rule_patch,
                                                  setup_state)
        if not setup_state.first_registration:
            raise ValueError('flask-restful blueprints can only be registered once.')
        self._init_app(setup_state.app)

    def _init_app(self, app):
        """Perform initialization actions with the given :class:`flask.Flask`
        object.

        :param app: The flask application object
        :type app: flask.Flask
        """
        if len(self.resources) > 0:
            for resource, urls, kwargs in self.resources:
                self._register_view(app, resource, *urls, **kwargs)

    def mediatypes_method(self):
        """Return a method that returns a list of mediatypes
        """
        return lambda resource_cls: self.mediatypes() + [self.default_mediatype]

    def add_resource(self, resource, *urls, **kwargs):
        """Adds a resource to the api.

        :param resource: the class name of your resource
        :type resource: :class:`Type[Resource]`

        :param urls: one or more url routes to match for the resource, standard
                     flask routing rules apply.  Any url variables will be
                     passed to the resource method as args.
        :type urls: str

        :param endpoint: endpoint name (defaults to :meth:`Resource.__name__.lower`
            Can be used to reference this route in :class:`fields.Url` fields
        :type endpoint: str

        :param resource_class_args: args to be forwarded to the constructor of
            the resource.
        :type resource_class_args: tuple

        :param resource_class_kwargs: kwargs to be forwarded to the constructor
            of the resource.
        :type resource_class_kwargs: dict

        Additional keyword arguments not specified above will be passed as-is
        to :meth:`flask.Flask.add_url_rule`.

        Examples::

            api.add_resource(HelloWorld, '/', '/hello')
            api.add_resource(Foo, '/foo', endpoint="foo")
            api.add_resource(FooSpecial, '/special/foo', endpoint="foo")

        """
        if self.app is not None:
            self._register_view(self.app, resource, *urls, **kwargs)
        else:
            self.resources.append((resource, urls, kwargs))

    def resource(self, *urls, **kwargs):
        """Wraps a :class:`~flask_rips.Resource` class, adding it to the
        api. Parameters are the same as :meth:`~flask_rips.Api.add_resource`.

        Example::

            app = Flask(__name__)
            api = restful.Api(app)

            @api.resource('/foo')
            class Foo(Resource):
                def get(self):
                    return 'Hello, World!'

        """

        def decorator(cls):
            self.add_resource(cls, *urls, **kwargs)
            return cls

        return decorator

    def _register_view(self, app, resource, *urls, **kwargs):
        endpoint = kwargs.pop('endpoint', None) or resource.__name__.lower()
        self.endpoints.add(endpoint)
        resource_class_args = kwargs.pop('resource_class_args', ())
        resource_class_kwargs = kwargs.pop('resource_class_kwargs', {})

        # NOTE: 'view_functions' is cleaned up from Blueprint class in Flask 1.0
        if endpoint in getattr(app, 'view_functions', {}):
            previous_view_class = app.view_functions[endpoint].__dict__['view_class']

            # if you override the endpoint with a different class, avoid the collision by raising an exception
            if previous_view_class != resource:
                raise ValueError(
                    'This endpoint (%s) is already set to the class %s.' % (endpoint, previous_view_class.__name__))

        resource.mediatypes = self.mediatypes_method()  # Hacky
        resource.endpoint = endpoint
        resource_func = self.output(resource.as_view(endpoint, *resource_class_args,
                                                     **resource_class_kwargs))

        for decorator in self.decorators:
            resource_func = decorator(resource_func)

        for url in urls:
            # If this Api has a blueprint
            if self.blueprint:
                # And this Api has been setup
                if self.blueprint_setup:
                    # Set the rule to a string directly, as the blueprint is already
                    # set up.
                    self.blueprint_setup.add_url_rule(url, view_func=resource_func, **kwargs)
                    continue
                else:
                    # Set the rule to a function that expects the blueprint prefix
                    # to construct the final url.  Allows deferment of url finalization
                    # in the case that the associated Blueprint has not yet been
                    # registered to an application, so we can wait for the registration
                    # prefix
                    rule = partial(self._complete_url, url)
            else:
                # If we've got no Blueprint, just build a url with no prefix
                rule = self._complete_url(url, '')
            # Add the url to the application or blueprint
            app.add_url_rule(rule, view_func=resource_func, **kwargs)

    def output(self, resource):
        """Wraps a resource (as a flask view function), for cases where the
        resource does not directly return a response object

        :param resource: The resource as a flask view function
        """

        @wraps(resource)
        def wrapper(*args, **kwargs):
            resp = resource(*args, **kwargs)
            if isinstance(resp, ResponseBase):  # There may be a better way to test
                return resp
            data, code, headers = unpack(resp)
            return self.make_response(data, code, headers=headers)

        return wrapper

    def url_for(self, resource, **values):
        """Generates a URL to the given resource.

        Works like :func:`flask.url_for`."""
        endpoint = resource.endpoint
        if self.blueprint:
            endpoint = '{0}.{1}'.format(self.blueprint.name, endpoint)
        return url_for(endpoint, **values)

    def make_response(self, data, *args, **kwargs):
        """Looks up the representation transformer for the requested media
        type, invoking the transformer to create a response object. This
        defaults to default_mediatype if no transformer is found for the
        requested mediatype. If default_mediatype is None, a 406 Not
        Acceptable response will be sent as per RFC 2616 section 14.1

        :param data: Python object containing response data to be transformed
        """
        default_mediatype = kwargs.pop('fallback_mediatype', None) or self.default_mediatype
        mediatype = request.accept_mimetypes.best_match(
            self.representations,
            default=default_mediatype,
        )
        if mediatype is None:
            raise NotAcceptable()
        if mediatype in self.representations:
            resp = self.representations[mediatype](data, *args, **kwargs)
            resp.headers['Content-Type'] = mediatype
            return resp
        elif mediatype == 'text/plain':
            resp = original_flask_make_response(str(data), *args, **kwargs)
            resp.headers['Content-Type'] = 'text/plain'
            return resp
        else:
            raise InternalServerError()

    def mediatypes(self):
        """Returns a list of requested mediatypes sent in the Accept header"""
        return [h for h, q in sorted(request.accept_mimetypes,
                                     key=operator.itemgetter(1), reverse=True)]

    def representation(self, mediatype):
        """Allows additional representation transformers to be declared for the
        api. Transformers are functions that must be decorated with this
        method, passing the mediatype the transformer represents. Three
        arguments are passed to the transformer:

        * The data to be represented in the response body
        * The http status code
        * A dictionary of headers

        The transformer should convert the data appropriately for the mediatype
        and return a Flask response object.

        Ex::

            @api.representation('application/xml')
            def xml(data, code, headers):
                resp = make_response(convert_data_to_xml(data), code)
                resp.headers.extend(headers)
                return resp
        """

        def wrapper(func):
            self.representations[mediatype] = func
            return func

        return wrapper

    def unauthorized(self, response):
        """ Given a response, change it to ask for credentials """

        if self.serve_challenge_on_401:
            realm = current_app.config.get("HTTP_BASIC_AUTH_REALM", "flask-restful")
            challenge = u"{0} realm=\"{1}\"".format("Basic", realm)

            response.headers['WWW-Authenticate'] = challenge
        return response


class Resource(MethodView):
    """
    Represents an abstract RESTful resource. Concrete resources should
    extend from this class and expose methods for each supported HTTP
    method. If a resource is invoked with an unsupported HTTP method,
    the API will return a response with status 405 Method Not Allowed.
    Otherwise the appropriate method is called and passed all arguments
    from the url rule used when adding the resource to an Api instance. See
    :meth:`~flask_rips.Api.add_resource` for details.
    """
    representations = None
    method_decorators = []

    def dispatch_request(self, *args, **kwargs):

        # Taken from flask
        # noinspection PyUnresolvedReferences
        meth = getattr(self, request.method.lower(), None)
        if meth is None and request.method == 'HEAD':
            meth = getattr(self, 'get', None)
        assert meth is not None, 'Unimplemented method %r' % request.method

        if isinstance(self.method_decorators, Mapping):
            decorators = self.method_decorators.get(request.method.lower(), [])
        else:
            decorators = self.method_decorators

        for decorator in decorators:
            meth = decorator(meth)

        resp = meth(*args, **kwargs)

        if isinstance(resp, ResponseBase):  # There may be a better way to test
            return resp

        representations = self.representations or OrderedDict()

        # noinspection PyUnresolvedReferences
        mediatype = request.accept_mimetypes.best_match(representations, default=None)
        if mediatype in representations:
            data, code, headers = unpack(resp)
            resp = representations[mediatype](data, code, headers)
            resp.headers['Content-Type'] = mediatype
            return resp

        return resp
