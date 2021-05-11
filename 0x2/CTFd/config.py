import configparser
import os
from distutils.util import strtobool


class EnvInterpolation(configparser.BasicInterpolation):
    """插值，它扩展了环境变量的值。"""

    def before_get(self, parser, section, option, value, defaults):
        value = super().before_get(parser, section, option, value, defaults)
        envvar = os.getenv(option)
        if value == "" and envvar:
            return process_string_var(envvar)
        else:
            return value


def process_string_var(value):
    if value == "":
        return None

    if value.isdigit():
        return int(value)
    elif value.replace(".", "", 1).isdigit():
        return float(value)

    try:
        return bool(strtobool(value))
    except ValueError:
        return value


def process_boolean_str(value):
    if type(value) is bool:
        return value

    if value is None:
        return False

    if value == "":
        return None

    return bool(strtobool(value))


def empty_str_cast(value, default=None):
    if value == "":
        return default
    return value


def gen_secret_key():
    # 试图从秘密文件中读取秘密
    # 如果秘密还没有被写入，这将会失败
    try:
        with open(".ctfd_secret_key", "rb") as secret:
            key = secret.read()
    except OSError:
        key = None

    if not key:
        key = os.urandom(64)
        # 试图写入秘密文件
        # 如果文件系统是只读的，这将会失败
        try:
            with open(".ctfd_secret_key", "wb") as secret:
                secret.write(key)
                secret.flush()
        except OSError:
            pass
    return key


config_ini = configparser.ConfigParser(interpolation=EnvInterpolation())
config_ini.optionxform = str  # 使得键值不区分大小写
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config_ini.read(path)


# fmt: off
class ServerConfig(object):
    SECRET_KEY: str = empty_str_cast(config_ini["server"]["SECRET_KEY"]) \
        or gen_secret_key()

    DATABASE_URL: str = empty_str_cast(config_ini["server"]["DATABASE_URL"]) \
        or f"sqlite:///{os.path.dirname(os.path.abspath(__file__))}/ctfd.db"

    REDIS_URL: str = empty_str_cast(config_ini["server"]["REDIS_URL"])

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    CACHE_REDIS_URL = REDIS_URL
    if CACHE_REDIS_URL:
        CACHE_TYPE: str = "redis"
    else:
        CACHE_TYPE: str = "filesystem"
        CACHE_DIR: str = os.path.join(
            os.path.dirname(__file__), os.pardir, ".data", "filesystem_cache"
        )
        # 覆盖文件系统上的缓存值的阈值。默认是500。除非你知道自己在做什么，否则不要改变。
        CACHE_THRESHOLD: int = 0

    # === SECURITY ===
    SESSION_COOKIE_HTTPONLY: bool = config_ini["security"].getboolean("SESSION_COOKIE_HTTPONLY", fallback=True)

    SESSION_COOKIE_SAMESITE: str = empty_str_cast(config_ini["security"]["SESSION_COOKIE_SAMESITE"]) \
        or "Lax"

    PERMANENT_SESSION_LIFETIME: int = config_ini["security"].getint("PERMANENT_SESSION_LIFETIME") \
        or 604800

    """
    trusted_proxies:
    定义了一组正则表达式，用于查找用户的IP地址，如果CTFd instance
    是在一个代理后面。如果你正在运行一个CTF，并且用户和你在同一个网络上，你可以选择从列表中删除
    列表中的一些代理。

    CTFd只使用IP地址进行粗略的跟踪。做任何复杂的事情都是不明智的。
    除非你知道自己在做什么。
    """
    TRUSTED_PROXIES = [
        r"^127\.0\.0\.1$",
        # Remove the following proxies if you do not trust the local network
        # For example if you are running a CTF on your laptop and the teams are
        # all on the same network
        r"^::1$",
        r"^fc00:",
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
        r"^192\.168\.",
    ]

    # === EMAIL ===
    MAILFROM_ADDR: str = config_ini["email"]["MAILFROM_ADDR"] \
        or "noreply@examplectf.com"

    MAIL_SERVER: str = empty_str_cast(config_ini["email"]["MAIL_SERVER"])

    MAIL_PORT: int = empty_str_cast(config_ini["email"]["MAIL_PORT"])

    MAIL_USEAUTH: bool = process_boolean_str(config_ini["email"]["MAIL_USEAUTH"])

    MAIL_USERNAME: str = empty_str_cast(config_ini["email"]["MAIL_USERNAME"])

    MAIL_PASSWORD: str = empty_str_cast(config_ini["email"]["MAIL_PASSWORD"])

    MAIL_TLS: bool = process_boolean_str(config_ini["email"]["MAIL_TLS"])

    MAIL_SSL: bool = process_boolean_str(config_ini["email"]["MAIL_SSL"])

    MAILSENDER_ADDR: str = empty_str_cast(config_ini["email"]["MAILSENDER_ADDR"])

    MAILGUN_API_KEY: str = empty_str_cast(config_ini["email"]["MAILGUN_API_KEY"])

    MAILGUN_BASE_URL: str = empty_str_cast(config_ini["email"]["MAILGUN_API_KEY"])

    # === LOGS ===
    LOG_FOLDER: str = empty_str_cast(config_ini["logs"]["LOG_FOLDER"]) \
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

    # === UPLOADS ===
    UPLOAD_PROVIDER: str = empty_str_cast(config_ini["uploads"]["UPLOAD_PROVIDER"]) \
        or "filesystem"

    UPLOAD_FOLDER: str = empty_str_cast(config_ini["uploads"]["UPLOAD_FOLDER"]) \
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

    if UPLOAD_PROVIDER == "s3":
        AWS_ACCESS_KEY_ID: str = empty_str_cast(config_ini["uploads"]["AWS_ACCESS_KEY_ID"])

        AWS_SECRET_ACCESS_KEY: str = empty_str_cast(config_ini["uploads"]["AWS_SECRET_ACCESS_KEY"])

        AWS_S3_BUCKET: str = empty_str_cast(config_ini["uploads"]["AWS_S3_BUCKET"])

        AWS_S3_ENDPOINT_URL: str = empty_str_cast(config_ini["uploads"]["AWS_S3_ENDPOINT_URL"])

    # === OPTIONAL ===
    REVERSE_PROXY: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["REVERSE_PROXY"], default=False))

    TEMPLATES_AUTO_RELOAD: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["TEMPLATES_AUTO_RELOAD"], default=True))

    THEME_FALLBACK: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["THEME_FALLBACK"], default=False))

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["SQLALCHEMY_TRACK_MODIFICATIONS"], default=False))

    SWAGGER_UI: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["SWAGGER_UI"], default=False))

    SWAGGER_UI_ENDPOINT: str = "/" if SWAGGER_UI else None

    UPDATE_CHECK: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["UPDATE_CHECK"], default=True))

    APPLICATION_ROOT: str = empty_str_cast(config_ini["optional"]["APPLICATION_ROOT"], default="/")

    SERVER_SENT_EVENTS: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["SERVER_SENT_EVENTS"], default=True))

    HTML_SANITIZATION: bool = process_boolean_str(empty_str_cast(config_ini["optional"]["HTML_SANITIZATION"], default=False))

    if DATABASE_URL.startswith("sqlite") is False:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "max_overflow": int(empty_str_cast(config_ini["optional"]["SQLALCHEMY_MAX_OVERFLOW"], default=20)),  # noqa: E131
            "pool_pre_ping": empty_str_cast(config_ini["optional"]["SQLALCHEMY_POOL_PRE_PING"], default=True),  # noqa: E131
        }

    # === OAUTH ===
    OAUTH_CLIENT_ID: str = empty_str_cast(config_ini["oauth"]["OAUTH_CLIENT_ID"])
    OAUTH_CLIENT_SECRET: str = empty_str_cast(config_ini["oauth"]["OAUTH_CLIENT_SECRET"])
# fmt: on


class TestingConfig(ServerConfig):
    SECRET_KEY = "AAAAAAAAAAAAAAAAAAAA"
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TESTING_DATABASE_URL") or "sqlite://"
    MAIL_SERVER = os.getenv("TESTING_MAIL_SERVER")
    SERVER_NAME = "localhost"
    UPDATE_CHECK = False
    REDIS_URL = None
    CACHE_TYPE = "simple"
    CACHE_THRESHOLD = 500
    SAFE_MODE = True


# 实际上是初始化ServerConfig，以使我们能够添加更多的属性在
Config = ServerConfig()
for k, v in config_ini.items("extra"):
    setattr(Config, k, process_string_var(v))
