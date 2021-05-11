CTFD源码简析

源地址：https://github.com/CTFd/CTFd

注释：

仅对根目录的文件进行了分析，理解了CTF比赛平台的框架和组成部分，具体功能实现待学习

```python
init.py

class CTFdRequest(Request):劫持原始的Flask请求路径
class CTFdFlask(Flask):覆盖的Jinja构造函数设置一个自定义的jinja_environment
class SandboxedBaseEnvironment(SandboxedEnvironment):模仿Flask BaseEnvironment的SandboxEnvironment。
class ThemeLoader(FileSystemLoader):主题结构和配置   
```

小收获

关于**import numpy**和**from numpy import \*** 

不推荐使用import \*，其没有明确地指出你使用了模块中的哪些类。

并且，如果导入了一个与程序文件中其他东西同名的类，会引发难以发现的错误。

```python
auth.py

#确认配置模块
@auth.route("/confirm", methods=["POST", "GET"])
#注册模块
@auth.route("/register", methods=["POST", "GET"])
#登录模块
@auth.route("/login", methods=["POST", "GET"])
#注销模块
@auth.route("/logout")
#修改密码模块
@auth.route("/reset_password", methods=["POST", "GET"])
#配置
@auth.route("/oauth")

```

```python
challenges.py

#题目信息页
@challenges.route("/challenges", methods=["GET"])

config.py
#具体配置信息

error.py
#意外报错信息

scoreboard.py
#计分板
@scoreboard.route("/scoreboard")

teams.py
#队伍创建，加入，邀请等细节处理
@teams.route("/teams")

user.py
#用户信息
@users.route("/users")

views.py
#项目部署时比赛信息的设置
@views.route("/setup", methods=["GET", "POST"])

config.ini
#配置文件，自带完整的注释
```

