import datetime
import os
import sys
import weakref
from distutils.version import StrictVersion

import jinja2
from flask import Flask, Request
from flask.helpers import safe_join
from flask_migrate import upgrade
from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import cached_property

import CTFd.utils.config
from CTFd import utils
from CTFd.constants.themes import ADMIN_THEME, DEFAULT_THEME
from CTFd.plugins import init_plugins
from CTFd.utils.crypto import sha256
from CTFd.utils.initialization import (
    init_events,
    init_logs,
    init_request_processors,
    init_template_filters,
    init_template_globals,
)
from CTFd.utils.migrations import create_database, migrations, stamp_latest_revision
from CTFd.utils.sessions import CachingSessionInterface
from CTFd.utils.updates import update_check

__version__ = "3.3.0"
__channel__ = "oss"


class CTFdRequest(Request):
    @cached_property
    def path(self):
        """
        Hijack the original Flask request path because it does not account for subdirectory deployments in an intuitive
        manner. We append script_root so that the path always points to the full path as seen in the browser.
        e.g. /subdirectory/path/route vs /path/route
        劫持原始的Flask请求路径，因为它没有以直观的方式考虑到子目录的部署。
        的方式。我们附加了script_root，使路径总是指向浏览器中看到的完整路径。
        例如：/subdirectory/path/route vs /path/route
        :return: string
        """
        return self.script_root + super(CTFdRequest, self).path


class CTFdFlask(Flask):
    def __init__(self, *args, **kwargs):
        """Overriden Jinja constructor setting a custom jinja_environment
        覆盖的Jinja构造函数设置一个自定义的jinja_environment"""
        self.jinja_environment = SandboxedBaseEnvironment
        self.session_interface = CachingSessionInterface(key_prefix="session")
        self.request_class = CTFdRequest

        # Store server start time
        self.start_time = datetime.datetime.utcnow()

        # Create generally unique run identifier 创建一般独特的运行标识符
        self.run_id = sha256(str(self.start_time))[0:8]
        Flask.__init__(self, *args, **kwargs)

    def create_jinja_environment(self):
        """Overridden jinja environment constructor
        重载的Jinja环境构造函数"""
        return super(CTFdFlask, self).create_jinja_environment()


class SandboxedBaseEnvironment(SandboxedEnvironment):
    """SandboxEnvironment that mimics the Flask BaseEnvironment
    模仿Flask BaseEnvironment的SandboxEnvironment。"""

    def __init__(self, app, **options):
        if "loader" not in options:
            options["loader"] = app.create_global_jinja_loader()
        SandboxedEnvironment.__init__(self, **options)
        self.app = app

    def _load_template(self, name, globals):
        if self.loader is None:
            raise TypeError("no loader for this environment specified")

        # Add theme to the LRUCache cache key
        cache_name = name
        if name.startswith("admin/") is False:
            theme = str(utils.get_config("ctf_theme"))
            cache_name = theme + "/" + name

        # Rest of this code is copied from Jinja
        # https://github.com/pallets/jinja/blob/master/src/jinja2/environment.py#L802-L815
        cache_key = (weakref.ref(self.loader), cache_name)
        if self.cache is not None:
            template = self.cache.get(cache_key)
            if template is not None and (
                not self.auto_reload or template.is_up_to_date
            ):
                return template
        template = self.loader.load(self, name, globals)
        if self.cache is not None:
            self.cache[cache_key] = template
        return template


class ThemeLoader(FileSystemLoader):
    """自定义FileSystemLoader，知道主题结构和配置。"""
    """Custom FileSystemLoader that is aware of theme structure and config."""
    

    DEFAULT_THEMES_PATH = os.path.join(os.path.dirname(__file__), "themes")
    _ADMIN_THEME_PREFIX = ADMIN_THEME + "/"

    def __init__(
        self,
        searchpath=DEFAULT_THEMES_PATH,
        theme_name=None,
        encoding="utf-8",
        followlinks=False,
    ):
        super(ThemeLoader, self).__init__(searchpath, encoding, followlinks)
        self.theme_name = theme_name

    def get_source(self, environment, template):
        # Refuse to load `admin/*` from a loader not for the admin theme
        # Because there is a single template loader, themes can essentially
        # provide files for other themes. This could end up causing issues if
        # an admin theme references a file that doesn't exist that a malicious
        # theme provides.
        # 拒绝从非管理员主题的加载器中加载`admin/*`。
        # 因为有一个单一的模板加载器，所以主题可以在本质上
        # 为其他主题提供文件。这可能会导致问题，如果
        # 一个管理员主题引用了一个不存在的文件，而这个文件是一个恶意的
        # 主题提供的文件。
        if template.startswith(self._ADMIN_THEME_PREFIX):
            if self.theme_name != ADMIN_THEME:
                raise jinja2.TemplateNotFound(template)
            template = template[len(self._ADMIN_THEME_PREFIX) :]
        theme_name = self.theme_name or str(utils.get_config("ctf_theme"))
        template = safe_join(theme_name, "templates", template)
        return super(ThemeLoader, self).get_source(environment, template)

#更新
def confirm_upgrade():
    if sys.stdin.isatty():
        print("/*\\ CTFd has updated and must update the database! /*\\")
        print("/*\\ Please backup your database before proceeding! /*\\")
        print("/*\\ CTFd maintainers are not responsible for any data loss! /*\\")
        if input("Run database migrations (Y/N)").lower().strip() == "y":  # nosec B322
            return True
        else:
            print("/*\\ Ignored database migrations... /*\\")
            return False
    else:
        return True


def run_upgrade():
    upgrade()
    utils.set_config("ctf_version", __version__)


def create_app(config="CTFd.config.Config"):
    app = CTFdFlask(__name__)
    with app.app_context():
        app.config.from_object(config)

        loaders = []
        # 我们提供了一个`DictLoader'，可以用来覆盖模板
        app.overridden_templates = {}
        loaders.append(jinja2.DictLoader(app.overridden_templates))
        # 没有`theme_name'的`ThemeLoader'将从当前主题加载。
        # A `ThemeLoader` with no `theme_name` will load from the current theme
        loaders.append(ThemeLoader())
        # 如果`THEME_FALLBACK`被设置为真，我们会添加另一个加载器，
        # 它将从 "DEFAULT_THEME "加载 - 这反映了由从`DEFAULT_THEME`加载，
        # 这反映了`config.ctf_theme_candidates()`实现的顺序。
        # If `THEME_FALLBACK` is set and true, we add another loader which will
        # load from the `DEFAULT_THEME` - this mirrors the order implemented by
        # `config.ctf_theme_candidates()`
        if bool(app.config.get("THEME_FALLBACK")):
            loaders.append(ThemeLoader(theme_name=DEFAULT_THEME))
        # All themes including admin can be accessed by prefixing their name
        # 所有的主题，包括管理，都可以通过前缀其名称来访问
        prefix_loader_dict = {ADMIN_THEME: ThemeLoader(theme_name=ADMIN_THEME)}
        for theme_name in CTFd.utils.config.get_themes():
            prefix_loader_dict[theme_name] = ThemeLoader(theme_name=theme_name)
        loaders.append(jinja2.PrefixLoader(prefix_loader_dict))
        # Plugin templates are also accessed via prefix but we just point a
        # normal `FileSystemLoader` at the plugin tree rather than validating
        # each plugin here (that happens later in `init_plugins()`). We
        # deliberately don't add this to `prefix_loader_dict` defined above
        # because to do so would break template loading from a theme called
        # `prefix` (even though that'd be weird).
        # 插件模板也可以通过前缀访问，但我们只是将一个
        # 普通的`FileSystemLoader'指向插件树，而不是在这里验证
        # 而不是在这里验证每个插件（这在后面的`init_plugins()'中发生）。我们
        # 故意不在上面定义的`prefix_loader_dict'中添加这个内容
        # 因为这样做会破坏主题的模板加载，称为
        # `prefix`（尽管那会很奇怪）。
        plugin_loader = jinja2.FileSystemLoader(
            searchpath=os.path.join(app.root_path, "plugins"), followlinks=True
        )
        loaders.append(jinja2.PrefixLoader({"plugins": plugin_loader}))
        # Use a choice loader to find the first match from our list of loaders
        app.jinja_loader = jinja2.ChoiceLoader(loaders)

        from CTFd.models import (  # noqa: F401
            db,
            Teams,
            Solves,
            Challenges,
            Fails,
            Flags,
            Tags,
            Files,
            Tracking,
        )

        url = create_database()

        # This allows any changes to the SQLALCHEMY_DATABASE_URI to get pushed back in
        # This is mostly so we can force MySQL's charset
        app.config["SQLALCHEMY_DATABASE_URI"] = str(url)

        # Register database
        db.init_app(app)

        # Register Flask-Migrate
        migrations.init_app(app, db)

        # Alembic sqlite support is lacking so we should just create_all anyway
        if url.drivername.startswith("sqlite"):
            # Enable foreign keys for SQLite. This must be before the
            # db.create_all call because tests use the in-memory SQLite
            # database (each connection, including db creation, is a new db).
            # https://docs.sqlalchemy.org/en/13/dialects/sqlite.html#foreign-key-support
            from sqlalchemy.engine import Engine
            from sqlalchemy import event

            @event.listens_for(Engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            db.create_all()
            stamp_latest_revision()
        else:
            # This creates tables instead of db.create_all()
            # Allows migrations to happen properly
            upgrade()

        from CTFd.models import ma

        ma.init_app(app)

        app.db = db
        app.VERSION = __version__
        app.CHANNEL = __channel__

        from CTFd.cache import cache

        cache.init_app(app)
        app.cache = cache

        reverse_proxy = app.config.get("REVERSE_PROXY")
        if reverse_proxy:
            if type(reverse_proxy) is str and "," in reverse_proxy:
                proxyfix_args = [int(i) for i in reverse_proxy.split(",")]
                app.wsgi_app = ProxyFix(app.wsgi_app, *proxyfix_args)
            else:
                app.wsgi_app = ProxyFix(
                    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
                )

        version = utils.get_config("ctf_version")

        # Upgrading from an older version of CTFd
        if version and (StrictVersion(version) < StrictVersion(__version__)):
            if confirm_upgrade():
                run_upgrade()
            else:
                exit()

        if not version:
            utils.set_config("ctf_version", __version__)

        if not utils.get_config("ctf_theme"):
            utils.set_config("ctf_theme", DEFAULT_THEME)

        update_check(force=True)

        init_request_processors(app)
        init_template_filters(app)
        init_template_globals(app)

        # 在这里导入允许测试使用合理的名称（例如，api而不是api_bp）。
        # Importing here allows tests to use sensible names (e.g. api instead of api_bp)
        from CTFd.views import views
        from CTFd.teams import teams
        from CTFd.users import users
        from CTFd.challenges import challenges
        from CTFd.scoreboard import scoreboard
        from CTFd.auth import auth
        from CTFd.admin import admin
        from CTFd.api import api
        from CTFd.events import events
        from CTFd.errors import render_error

        app.register_blueprint(views)
        app.register_blueprint(teams)
        app.register_blueprint(users)
        app.register_blueprint(challenges)
        app.register_blueprint(scoreboard)
        app.register_blueprint(auth)
        app.register_blueprint(api)
        app.register_blueprint(events)

        app.register_blueprint(admin)

        for code in {403, 404, 500, 502}:
            app.register_error_handler(code, render_error)

        init_logs(app)
        init_events(app)
        init_plugins(app)

        return app
