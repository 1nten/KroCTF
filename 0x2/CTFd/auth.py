import base64
import requests
from flask import Blueprint
from flask import current_app as app
from flask import redirect, render_template, request, session, url_for
from itsdangerous.exc import BadSignature, BadTimeSignature, SignatureExpired
from CTFd.cache import clear_team_session, clear_user_session
from CTFd.models import Teams, UserFieldEntries, UserFields, Users, db
from CTFd.utils import config, email, get_app_config, get_config
from CTFd.utils import user as current_user
from CTFd.utils import validators
from CTFd.utils.config import is_teams_mode
from CTFd.utils.config.integrations import mlc_registration
from CTFd.utils.config.visibility import registration_visible
from CTFd.utils.crypto import verify_password
from CTFd.utils.decorators import ratelimit
from CTFd.utils.decorators.visibility import check_registration_visibility
from CTFd.utils.helpers import error_for, get_errors, markup
from CTFd.utils.logging import log
from CTFd.utils.modes import TEAMS_MODE
from CTFd.utils.security.auth import login_user, logout_user
from CTFd.utils.security.signing import unserialize
from CTFd.utils.validators import ValidationError

auth = Blueprint("auth", __name__)
#确认配置模块
@auth.route("/confirm", methods=["POST", "GET"])
@auth.route("/confirm/<data>", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=60)
def confirm(data=None):
    if not get_config("verify_emails"):
        #如果CTF不关心确认电子邮件地址，那么就重拨挑战。
        # If the CTF doesn't care about confirming email addresses then redierct to challenges
        return redirect(url_for("challenges.listing"))
    # 用户正在确认电子邮件帐户
    # User is confirming email account
    if data and request.method == "GET":
        try:
            user_email = unserialize(data, max_age=1800)
        except (BadTimeSignature, SignatureExpired):
            return render_template(
                "confirm.html", errors=["您的确认链接已经过期。Your confirmation link has expired"]
            )
        except (BadSignature, TypeError, base64.binascii.Error):
            return render_template(
                "confirm.html", errors=["你的确认令牌是无效的。Your confirmation token is invalid"]
            )

        user = Users.query.filter_by(email=user_email).first_or_404()
        if user.verified:
            return redirect(url_for("views.settings"))
        #成功确认
        user.verified = True
        log(
            "registrations",
            format="[{date}] {ip} - successful confirmation for {name}",
            name=user.name,
        )
        db.session.commit()
        clear_user_session(user_id=user.id)
        email.successful_registration_notification(user.email)
        db.session.close()
        if current_user.authed():
            return redirect(url_for("challenges.listing"))
        return redirect(url_for("auth.login"))
    #用户正试图启动或重新启动确认流程
    # User is trying to start or restart the confirmation flow
    if current_user.authed() is False:
        return redirect(url_for("auth.login"))

    user = Users.query.filter_by(id=session["id"]).first_or_404()
    if user.verified:
        return redirect(url_for("views.settings"))

    if data is None:
        if request.method == "POST":
            #用户希望重新发送他们的确认邮件
            # User wants to resend their confirmation email
            email.verify_email_address(user.email)
            log(
                "registrations",
                format="[{date}] {ip} - {name} initiated a confirmation email resend",
                name=user.name,
            )
            return render_template(
                "confirm.html", infos=[f"Confirmation email sent to {user.email}!"]
            )
        elif request.method == "GET":
            #用户已被引导至确认页面
            # User has been directed to the confirm page
            return render_template("confirm.html")


#注册模块
@auth.route("/register", methods=["POST", "GET"])
@check_registration_visibility
@ratelimit(method="POST", limit=10, interval=5)
def register():
    errors = get_errors()
    #重定向
    if current_user.authed():
        return redirect(url_for("challenges.listing"))
    #提交表单后获取注册信息
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email_address = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        website = request.form.get("website")
        affiliation = request.form.get("affiliation")
        country = request.form.get("country")

        name_len = len(name) == 0
        names = Users.query.add_columns("name", "id").filter_by(name=name).first()
        emails = (
            Users.query.add_columns("email", "id")
            .filter_by(email=email_address)
            .first()
        )
        #校验密码，邮箱是否合理
        pass_short = len(password) == 0
        pass_long = len(password) > 128
        valid_email = validators.validate_email(email_address)
        team_name_email_check = validators.validate_email(name)

        # 处理额外的用户字段
        fields = {}
        for field in UserFields.query.all():
            fields[field.id] = field

        entries = {}
        for field_id, field in fields.items():
            value = request.form.get(f"fields[{field_id}]", "").strip()
            if field.required is True and (value is None or value == ""):
                errors.append("请提供所有必填项。Please provide all required fields")
                break

            # Handle special casing of existing profile fields
            if field.name.lower() == "affiliation":
                affiliation = value
                break
            elif field.name.lower() == "website":
                website = value
                break

            if field.field_type == "boolean":
                entries[field_id] = bool(value)
            else:
                entries[field_id] = value
        #校验信息
        if country:
            try:
                validators.validate_country_code(country)
                valid_country = True
            except ValidationError:
                valid_country = False
        else:
            valid_country = True

        if website:
            valid_website = validators.validate_url(website)
        else:
            valid_website = True

        if affiliation:
            valid_affiliation = len(affiliation) < 128
        else:
            valid_affiliation = True

        if not valid_email:
            errors.append("Please enter a valid email address")
        if email.check_email_is_whitelisted(email_address) is False:
            errors.append(
                "Only email addresses under {domains} may register".format(
                    domains=get_config("domain_whitelist")
                )
            )
        if names:
            errors.append("That user name is already taken")
        if team_name_email_check is True:
            errors.append("Your user name cannot be an email address")
        if emails:
            errors.append("That email has already been used")
        if pass_short:
            errors.append("Pick a longer password")
        if pass_long:
            errors.append("Pick a shorter password")
        if name_len:
            errors.append("Pick a longer user name")
        if valid_website is False:
            errors.append("Websites must be a proper URL starting with http or https")
        if valid_country is False:
            errors.append("Invalid country")
        if valid_affiliation is False:
            errors.append("Please provide a shorter affiliation")
        #如果有错误就重试
        if len(errors) > 0:
            return render_template(
                "register.html",
                errors=errors,
                name=request.form["name"],
                email=request.form["email"],
                password=request.form["password"],
            )
        #保存注册信息
        else:
            with app.app_context():
                user = Users(name=name, email=email_address, password=password)

                if website:
                    user.website = website
                if affiliation:
                    user.affiliation = affiliation
                if country:
                    user.country = country

                db.session.add(user)
                db.session.commit()
                db.session.flush()

                for field_id, value in entries.items():
                    entry = UserFieldEntries(
                        field_id=field_id, value=value, user_id=user.id
                    )
                    db.session.add(entry)
                db.session.commit()

                login_user(user)

                if request.args.get("next") and validators.is_safe_url(
                    request.args.get("next")
                ):
                    return redirect(request.args.get("next"))

                if config.can_send_mail() and get_config(
                    "verify_emails"
                ):  # 确认用户已启用，我们可以发送电子邮件。
                    log(
                        "registrations",
                        format="[{date}] {ip} - {name} registered (UNCONFIRMED) with {email}",
                        name=user.name,
                        email=user.email,
                    )
                    email.verify_email_address(user.email)
                    db.session.close()
                    return redirect(url_for("auth.confirm"))
                else:  #  不关心确认用户的情况
                    if (
                        config.can_send_mail()
                    ):  # 我们想通知用户，他们已经注册。
                        email.successful_registration_notification(user.email)

        log(
            "registrations",
            format="[{date}] {ip} - {name} registered with {email}",
            name=user.name,
            email=user.email,
        )
        db.session.close()
        #跳转
        if is_teams_mode():
            return redirect(url_for("teams.private"))

        return redirect(url_for("challenges.listing"))
    else:
        return render_template("register.html", errors=errors)

#登录模块
@auth.route("/login", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=5)
def login():
    errors = get_errors()
    if request.method == "POST":
        name = request.form["name"]

        # 检查用户是否提交了一个电子邮件地址或一个团队名称
        if validators.validate_email(name) is True:
            user = Users.query.filter_by(email=name).first()
        else:
            user = Users.query.filter_by(name=name).first()

         if user:
            if user and verify_password(request.form["password"], user.password):
                #登录成功
                session.regenerate()

                login_user(user)
                log("logins", "[{date}] {ip} - {name} logged in", name=user.name)

                db.session.close()
                if request.args.get("next") and validators.is_safe_url(
                    request.args.get("next")
                ):
                    return redirect(request.args.get("next"))
                return redirect(url_for("challenges.listing"))

            else:
                # 这个用户存在，但密码是错误的
                log(
                    "logins",
                    "[{date}] {ip} - submitted invalid password for {name}",
                    name=user.name,
                )
                errors.append("Your username or password is incorrect")
                db.session.close()
                return render_template("login.html", errors=errors)
        else:
            # 这个用户根本就不存在
            log("logins", "[{date}] {ip} - submitted invalid account information")
            errors.append("Your username or password is incorrect")
            db.session.close()
            return render_template("login.html", errors=errors)
    else:
        #其他错误
        db.session.close()
        return render_template("login.html", errors=errors)

#注销模块
@auth.route("/logout")
def logout():
    if current_user.authed():
        logout_user()
    return redirect(url_for("views.static_html"))


#修改密码模块
@auth.route("/reset_password", methods=["POST", "GET"])
@auth.route("/reset_password/<data>", methods=["POST", "GET"])
@ratelimit(method="POST", limit=10, interval=60)
def reset_password(data=None):
    #检测电子邮件是否成功配置
    if config.can_send_mail() is False:
        return render_template(
            "reset_password.html",
            errors=[
                markup(
                    "这个CTF没有被配置为发送电子邮件。请联系组织者，重新设置你的密码。This CTF is not configured to send email.<br> Please contact an organizer to have your password reset."
                )
            ],
        )
    if data is not None:
        try:
            email_address = unserialize(data, max_age=1800)
        except (BadTimeSignature, SignatureExpired):
            return render_template(
                "reset_password.html", errors=["您的链接已经过期。Your link has expired"]
            )
        except (BadSignature, TypeError, base64.binascii.Error):
            return render_template(
                "reset_password.html", errors=["你的重置令牌无效。Your reset token is invalid"]
            )
        #
        if request.method == "GET":
            return render_template("reset_password.html", mode="set")
        if request.method == "POST":
            password = request.form.get("password", "").strip()
            user = Users.query.filter_by(email=email_address).first_or_404()
            if user.oauth_id:
                return render_template(
                    "reset_password.html",
                    infos=[
                        "您的账户是通过认证供应商注册的，没有相关的密码。请通过您的认证供应商登录。Your account was registered via an authentication provider and does not have an associated password. Please login via your authentication provider."
                    ],
                )

            pass_short = len(password) == 0
            if pass_short:
                return render_template(
                    "reset_password.html", errors=["请选择一个较长的密码。Please pick a longer password"]
                )

            user.password = password
            db.session.commit()
            clear_user_session(user_id=user.id)
            log(
                "logins",
                format="[{date}] {ip} - successful password reset for {name}",
                name=user.name,
            )
            db.session.close()
            email.password_change_alert(user.email)
            return redirect(url_for("auth.login"))        
    if request.method == "POST":
        email_address = request.form["email"].strip()
        user = Users.query.filter_by(email=email_address).first()

        get_errors()

        if not user:
            return render_template(
                "reset_password.html",
                infos=[
                    "如果该账户存在，您将收到一封邮件，请检查您的收件箱。If that account exists you will receive an email, please check your inbox"
                ],
            )
        if user.oauth_id:
            return render_template(
                "reset_password.html",
                infos=[
                    "与此账户相关的电子邮件地址是通过认证供应商注册的，没有相关的密码。请通过您的认证供应商登录。"The email address associated with this account was registered via an authentication provider and does not have an associated password. Please login via your authentication provider."
                ],
            )
        email.forgot_password(email_address)

        return render_template(
            "reset_password.html",
            infos=[
                "如果该账户存在，你会收到一封邮件，请检查你的收件箱。If that account exists you will receive an email, please check your inbox"
            ],
        )
    return render_template("reset_password.html")


#配置
@auth.route("/oauth")
def oauth_login():
    endpoint = (
        get_app_config("OAUTH_AUTHORIZATION_ENDPOINT")
        or get_config("oauth_authorization_endpoint")
        or "https://auth.majorleaguecyber.org/oauth/authorize"
    )

    if get_config("user_mode") == "teams":
        scope = "profile team"
    else:
        scope = "profile"

    client_id = get_app_config("OAUTH_CLIENT_ID") or get_config("oauth_client_id")

    if client_id is None:
        error_for(
            endpoint="auth.login",
            message="OAuth Settings not configured. "
            "请你的CTF管理员配置MajorLeagueCyber整合。Ask your CTF administrator to configure MajorLeagueCyber integration.",
        )
        return redirect(url_for("auth.login"))

    redirect_url = "{endpoint}?response_type=code&client_id={client_id}&scope={scope}&state={state}".format(
        endpoint=endpoint, client_id=client_id, scope=scope, state=session["nonce"]
    )
    return redirect(redirect_url)

#注册验证模块
@auth.route("/redirect", methods=["GET"])
@ratelimit(method="GET", limit=10, interval=60)
def oauth_redirect():
    oauth_code = request.args.get("code")
    state = request.args.get("state")
    if session["nonce"] != state:
        log("logins", "[{date}] {ip} - OAuth状态验证不匹配 OAuth State validation mismatch")
        error_for(endpoint="auth.login", message="OAuth状态验证不匹配 OAuth State validation mismatch.")
        #返回登录界面
        return redirect(url_for("auth.login"))

    if oauth_code:
        url = (
            get_app_config("OAUTH_TOKEN_ENDPOINT")
            or get_config("oauth_token_endpoint")
            or "https://auth.majorleaguecyber.org/oauth/token"
        )

        client_id = get_app_config("OAUTH_CLIENT_ID") or get_config("oauth_client_id")
        client_secret = get_app_config("OAUTH_CLIENT_SECRET") or get_config(
            "oauth_client_secret"
        )
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {
            "code": oauth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
        }
        token_request = requests.post(url, data=data, headers=headers)

        if token_request.status_code == requests.codes.ok:
            token = token_request.json()["access_token"]
            user_url = (
                get_app_config("OAUTH_API_ENDPOINT")
                or get_config("oauth_api_endpoint")
                or "https://api.majorleaguecyber.org/user"
            )

            headers = {
                "Authorization": "Bearer " + str(token),
                "Content-type": "application/json",
            }
            api_data = requests.get(url=user_url, headers=headers).json()

            user_id = api_data["id"]
            user_name = api_data["name"]
            user_email = api_data["email"]

            user = Users.query.filter_by(email=user_email).first()
            if user is None:
                # 在创建用户之前检查我们是否允许注册
                if registration_visible() or mlc_registration():
                    user = Users(
                        name=user_name,
                        email=user_email,
                        oauth_id=user_id,
                        verified=True,
                    )
                    db.session.add(user)
                    db.session.commit()
                else:
                    log("logins", "[{date}] {ip} - Public registration via MLC blocked")
                    error_for(
                        endpoint="auth.login",
                        message="公共注册已被禁用。请稍后再试。Public registration is disabled. Please try again later.",
                    )
                    return redirect(url_for("auth.login"))

            if get_config("user_mode") == TEAMS_MODE:
                team_id = api_data["team"]["id"]
                team_name = api_data["team"]["name"]

                team = Teams.query.filter_by(oauth_id=team_id).first()
                if team is None:
                    team = Teams(name=team_name, oauth_id=team_id, captain_id=user.id)
                    db.session.add(team)
                    db.session.commit()
                    clear_team_session(team_id=team.id)

                team_size_limit = get_config("team_size", default=0)
                if team_size_limit and len(team.members) >= team_size_limit:
                    plural = "" if team_size_limit == 1 else "s"
                    size_error = "Teams are limited to {limit} member{plural}.".format(
                        limit=team_size_limit, plural=plural
                    )
                    error_for(endpoint="auth.login", message=size_error)
                    return redirect(url_for("auth.login"))

                team.members.append(user)
                db.session.commit()

            if user.oauth_id is None:
                user.oauth_id = user_id
                user.verified = True
                db.session.commit()
                clear_user_session(user_id=user.id)

            login_user(user)

            return redirect(url_for("challenges.listing"))
        else:
            log("logins", "[{date}] {ip} - OAuth token retrieval failure")
            error_for(endpoint="auth.login", message="OAuth token retrieval failure.")
            return redirect(url_for("auth.login"))
    else:
        log("logins", "[{date}] {ip} - Received redirect without OAuth code")
        error_for(
            endpoint="auth.login", message="Received redirect without OAuth code."
        )
        return redirect(url_for("auth.login"))
      