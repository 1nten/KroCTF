### FLASK

安装与快速启动

https://flask.palletsprojects.com/en/1.1.x/

#### helloword测试


创建hello.py

```python
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello, World!'
```

```sh
$ export FLASK_APP=hello.py
$ export FLASK_ENV=development  #调试模式
$ python3 -m flask run 
```

#### 博客

效果图

![image-20210424105825920](https://www.kro1lsec.com:442/images/2021/04/24/20210424105833.png)

##### 运行

新建项目flaskr

```sh
$ flask init-db        #初始化数据库
Initialized the database.
```


```sh
$ export FLASK_APP=flaskr   #linux
$ export FLASK_ENV=development
$ flask run
```

```sh
# cmd
> set FLASK_APP=flaskr
> set FLASK_ENV=development
> flask run

#PowerShell
> $env:FLASK_APP = "flaskr"
> $env:FLASK_ENV = "development"
> flask run
```

##### 测试

```sh
pytest tests
```

#### 构建和安装

[Deploy to Production — Flask Documentation (1.1.x) (palletsprojects.com)](https://flask.palletsprojects.com/en/1.1.x/tutorial/deploy/)



