# Github

## Git基本操作

初次使用需要配置好邮箱用户名，ssh或token

https://docs.github.com/cn/github/getting-started-with-github/quickstart

### 大致流程

1.链接

2.增删改查

3.提交更改

4.提交分支

```sh
echo "# KroCTF" >> README.md
git init
git add README.md
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/1nten/KroCTF.git
git push -u origin main
```

### 配置

```sh
$ git config --global user.email "email@example.com"
$ git config --global user.name "Mona Lisa"

$ git config --global user.name
$ git config --global user.email
```

### 基础信息

```csharp
//显示工作目录和暂存区的状态
$ git status
//显示日志（项目历史的信息）
$ git log
//将分支new1同步到云端GitHub    
$ git push origin new1
//克隆
$ git clone https://github.com/1nten/codeql.git
//初始化
$ git init
```

### 链接

```csharp
//创建链接origin
$ git remote add origin https://github.com/1nten/test1.git
//删除链接origin
$ git remote rm origin
```

### 分支

```csharp
//创建分支new1
$ git branch new1
//切换分支new1
$ git checkout new1
//删除本地分支new1
$ git branch --delete new1
//删除远程分支new1
$ git push origin --delete new1
//合并分支
61445@Social MINGW64 ~/Desktop/github (new1)
$ git checkout main
Switched to branch 'main'

61445@Social MINGW64 ~/Desktop/github (main)
$ git merge new1
Updating 94b56ea..ee28bef
Fast-forward
 test.md  | 1 +
 test.txt | 1 -
 2 files changed, 1 insertion(+), 1 deletion(-)
 create mode 100644 test.md
 delete mode 100644 test.txt  
```

### 文件

```csharp
//创建文件test.md
$ echo "## hello git" >> test.md
//添加文件test.md
$ git add test.md
//提交更改文件test.md
$ git commit -m "这是个测试文件" test.md
//将分支new1同步到云端GitHub    
$ git push origin new1

//删除文件test.txt
$ git rm test.txt
//提交更改文件test.txt
$ git commit -m "这是个测试文件" test.txt
//将分支new1同步到云端GitHub   
$ git push origin new1
```

### 调试信息

![image-20210412214552763](http://www.kro1lsec.com:8080/images/2021/04/12/20210412214608.png)

![image-20210412214658425](http://www.kro1lsec.com:8080/images/2021/04/12/20210412215305.png)

## 参考链接

[【git】- 将本地项目关联到github远程仓库]: https://zhuanlan.zhihu.com/p/88246764

[官方文档]: https://docs.github.com/cn/github/getting-started-with-github/quickstart

https://training.github.com/downloads/zh_CN/github-git-cheat-sheet/