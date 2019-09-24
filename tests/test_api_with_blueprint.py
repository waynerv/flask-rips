import unittest
from flask import Flask, Blueprint, request
try:
    from mock import Mock
except:
    # python3
    from unittest.mock import Mock
import flask
import flask_rips
#noinspection PyUnresolvedReferences
from nose.tools import assert_true, assert_false  # you need it for tests in form of continuations


# Add a dummy Resource to verify that the app is properly set.
class HelloWorld(flask_rips.Resource):
    def get(self):
        return {}


class GoodbyeWorld(flask_rips.Resource):
    def __init__(self, err):
        self.err = err

    def get(self):
        flask.abort(self.err)


class APIWithBlueprintTestCase(unittest.TestCase):

    def test_api_base(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api(blueprint)
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        self.assertEquals(api.urls, {})
        self.assertEquals(api.prefix, '')
        self.assertEquals(api.default_mediatype, 'application/json')

    def test_api_delayed_initialization(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api()
        api.init_app(blueprint)
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        api.add_resource(HelloWorld, '/', endpoint="hello")

    def test_add_resource_endpoint(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api(blueprint)
        view = Mock(**{'as_view.return_value': Mock(__name__='test_view')})
        api.add_resource(view, '/foo', endpoint='bar')
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        view.as_view.assert_called_with('bar')

    def test_add_resource_endpoint_after_registration(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api(blueprint)
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        view = Mock(**{'as_view.return_value': Mock(__name__='test_view')})
        api.add_resource(view, '/foo', endpoint='bar')
        view.as_view.assert_called_with('bar')

    def test_url_with_api_prefix(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api(blueprint, prefix='/api')
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        with app.test_request_context('/api/hi'):
            self.assertEquals(request.endpoint, 'test.hello')

    def test_url_with_blueprint_prefix(self):
        blueprint = Blueprint('test', __name__, url_prefix='/bp')
        api = flask_rips.Api(blueprint)
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        with app.test_request_context('/bp/hi'):
            self.assertEquals(request.endpoint, 'test.hello')

    def test_url_with_registration_prefix(self):
        blueprint = Blueprint('test', __name__)
        api = flask_rips.Api(blueprint)
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint, url_prefix='/reg')
        with app.test_request_context('/reg/hi'):
            self.assertEquals(request.endpoint, 'test.hello')

    def test_registration_prefix_overrides_blueprint_prefix(self):
        blueprint = Blueprint('test', __name__, url_prefix='/bp')
        api = flask_rips.Api(blueprint)
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint, url_prefix='/reg')
        with app.test_request_context('/reg/hi'):
            self.assertEquals(request.endpoint, 'test.hello')

    def test_url_with_api_and_blueprint_prefix(self):
        blueprint = Blueprint('test', __name__, url_prefix='/bp')
        api = flask_rips.Api(blueprint, prefix='/api')
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        with app.test_request_context('/bp/api/hi'):
            self.assertEquals(request.endpoint, 'test.hello')

    def test_url_part_order_aeb(self):
        blueprint = Blueprint('test', __name__, url_prefix='/bp')
        api = flask_rips.Api(blueprint, prefix='/api', url_part_order='aeb')
        api.add_resource(HelloWorld, '/hi', endpoint='hello')
        app = Flask(__name__)
        app.register_blueprint(blueprint)
        with app.test_request_context('/api/hi/bp'):
            self.assertEquals(request.endpoint, 'test.hello')


if __name__ == '__main__':
    unittest.main()
