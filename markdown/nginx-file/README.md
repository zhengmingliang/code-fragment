# Nginx 实战指南：仅需两步，打造安全又简单的私人文件服务器

### 前言

大家好！在日常开发和运维中，我们经常有这样的需求：快速搭建一个临时的文件服务器，用于分享构建产物、日志文件或者一些公共资源。同时，我们希望这个服务器不是完全公开的，至少能通过简单的密码进行保护。

传统的做法可能是启动一个 Python 的 `SimpleHTTPServer`，或者使用 `vsftpd` 等工具，但这些要么功能太简陋，要么配置稍嫌麻烦。

今天，我们就来介绍一种极其简单高效的方案：**使用 Nginx 搭建一个带有 Basic Auth 密码认证的文件服务器**。整个过程只需两步，让你轻松拥有一个安全、可靠的“私人网盘”。

---

### 效果预览

配置完成后，当有人访问你的文件服务器时，浏览器会弹出一个登录窗口，只有输入正确的用户名和密码才能看到文件列表。

![认证弹窗](https://cdn.dog.alianga.com/2025/10/20/3cf5d944a8ededa5.png)


*(这是一个效果示意图，实际样式可能因浏览器而异)*

成功登录后，会看到一个类似 Apache 目录浏览的简洁页面：

![文件列表](https://cdn.dog.alianga.com/2025/10/20/7c760f3b80ec396b.png)

### 用户访问示意图


![](https://cdn.dog.alianga.com/2025/10/20/1987a41f03913877.png)
---

### 第一步：配置 Nginx 成为文件服务器

首先，我们需要让 Nginx 指向一个特定的目录，并开启目录浏览功能。这非常简单。

假设你想分享的文件夹是 `/data/shared-files`，你只需要在 Nginx 的配置文件（通常是 `/etc/nginx/nginx.conf` 或 `/etc/nginx/conf.d/default.conf`）中添加一个 `server` 或 `location` 块。

```nginx
server {
    listen 15001; # 为了安全，避免使用默认的80端口
    server_name your.server.ip.or.domain;

    # 核心配置：文件服务器
    location / {
        root /data/shared-files;   # 指定文件存放的根目录
        autoindex on;              # 开启目录浏览功能！
        autoindex_exact_size off;  # 文件大小显示为易读的 KB/MB/GB
        autoindex_localtime on;    # 文件时间显示为服务器本地时间
        charset utf-8,gbk;         # 避免中文文件名乱码
    }
}
```

**配置项解释：**

*   `listen 8080`: 监听 8080 端口。
*   `root /data/shared-files`: 这是关键，指定了文件服务器的根目录。所有文件都将从这里提供。
*   `autoindex on`: 开启 Nginx 的目录自动索引功能，当访问一个目录时，会列出该目录下的所有文件和子目录。
*   `autoindex_exact_size off`: 将文件大小显示得更人性化（例如 `1.2M` 而不是 `1234567` 字节）。
*   `autoindex_localtime on`: 显示文件修改时间为服务器的本地时间，而不是 GMT 时间。
*   `charset utf-8,gbk`: 解决中文文件名可能出现的乱码问题。

配置完成后，记得创建一个用于测试的目录和文件：

```bash
# 创建共享目录
sudo mkdir -p /data/shared-files

# 放一个测试文件进去
echo "Hello, Nginx File Server!" | sudo tee /data/shared-files/test.txt
```

然后，重新加载 Nginx 配置：

```bash
sudo nginx -t  # 检查配置语法是否正确
sudo nginx -s reload # 重新加载配置
```

现在，通过 `http://your.server.ip.or.domain:8080` 访问，你应该已经能看到 `/data/shared-files` 目录下的 `test.txt` 文件了！

---

### 第二步：添加 Basic Auth 密码认证

我们的文件服务器已经可以工作了，但它是完全公开的。接下来，我们为它加上一道安全门。

Basic Authentication 是 HTTP 协议内建的一种简单认证方式。它不依赖于复杂的应用层逻辑，配置起来非常方便。

<!-- 在这里插入 image1.html 的截图 -->
**（此处请将 `image1.html` 在浏览器中打开并截图替换）**

#### 1. 生成密码文件

我们需要一个密码文件来存储授权访问的用户名和密码。通常有两种方式生成。

**方式一：使用 `htpasswd` 工具（推荐）**

`htpasswd` 是 Apache 的一个工具，专门用于创建和更新 Basic Auth 的密码文件。它通常包含在 `apache2-utils` 或 `httpd-tools` 包里。

**对于 Debian/Ubuntu 系统：**
```bash
sudo apt update
sudo apt install apache2-utils
```

**对于 CentOS/RHEL 系统：**
```bash
sudo yum install httpd-tools
```

**方式二：使用在线生成工具（更便捷）**

如果你没有服务器的 root 权限，或者不想安装额外的软件包，也可以直接使用在线工具来生成所需的内容。

这里推荐一个：[https://tool.oschina.net/htpasswd](https://tool.oschina.net/htpasswd)

只需输入用户名和密码，它会自动生成加密后的字符串，你只需要将生成的内容复制并粘贴到服务器的密码文件中即可。

![](https://cdn.dog.alianga.com/2025/10/20/eb1d1c949362d50b.png)

#### 2. 创建密码文件

现在，我们来创建一个用户和密码。假设我们想创建一个用户名为 `admin` 的用户。

执行以下命令，它会提示你输入密码：

```bash
# -c 参数表示创建一个新文件，只在第一次创建时使用！
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

> **注意：**
> *   `-c` 参数会覆盖已有文件。如果你想**添加第二个用户**，请**不要**带 `-c` 参数，例如：`sudo htpasswd /etc/nginx/.htpasswd user2`。
> *   密码文件 `.htpasswd` 的存放位置可以任意，但建议放在 Nginx 配置目录（如 `/etc/nginx/`）下，并确保 Nginx 进程有权限读取它。

执行后，可以查看一下文件内容，你会发现密码是加密存储的：

```bash
$ cat /etc/nginx/.htpasswd
admin:$apr1$b5v...$HqgW9aX.PT3.b1g/B.SgM.
```

#### 3. 修改 Nginx 配置，启用认证

最后一步，回到我们之前的 Nginx 配置文件，在 `location` 块中加入两行指令：

```nginx
server {
    listen 15001;
    server_name your.server.ip.or.domain;

    location / {
        root /data/shared-files;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
        charset utf-8,gbk;

        # 新增内容：开启 Basic Auth
        auth_basic "Restricted Area"; # 弹窗的提示信息
        auth_basic_user_file /etc/nginx/.htpasswd; # 指向刚刚创建的密码文件
    }
}
```

*   `auth_basic "Restricted Area"`: 这句话定义了弹出的登录框上显示的提示文本。你可以自定义成任何内容，例如 "请输入用户名和密码"。
*   `auth_basic_user_file`: 指定了包含用户名和密码的文件路径。

同样，修改配置后需要重新加载 Nginx：

```bash
sudo nginx -t && sudo nginx -s reload
```

---

### 大功告成！

现在，再次访问 `http://your.server.ip.or.domain:15001`，你的浏览器就会弹出那个熟悉的认证窗口了。输入你设置的 `admin` 用户和密码，验证通过后，即可看到你的文件列表。

## 番外篇：美化你的文件列表页面

![](https://cdn.dog.alianga.com/2025/10/20/6b32f84dd6bfb895.png)

Nginx 默认的 `autoindex` 页面虽然实用，但颜值确实有点“复古”。要实现美化，我们首先需要为 Nginx 安装一个强大的第三方模块——`ngx-fancyindex`，因为 `Nginxy` 主题依赖它才能工作。

### 前提：安装 `ngx-fancyindex` 模块

如果你的 Nginx 没有安装这个模块，直接在配置中使用 `fancyindex on;` 指令会导致 Nginx 启动失败。安装第三方模块通常需要重新编译 Nginx 或将其作为动态模块添加。下面是动态添加模块的通用步骤（以 Debian/Ubuntu 为例），这种方式无需重装 Nginx。

**1. 准备编译环境**

```bash
# 安装编译所需的工具
sudo apt update
sudo apt install -y build-essential libpcre3-dev zlib1g-dev libssl-dev

# 下载 ngx-fancyindex 模块源码
sudo git clone https://github.com/aperezdc/ngx-fancyindex.git /opt/ngx-fancyindex
```

**2. 获取当前 Nginx 版本和配置参数**

这一步至关重要，我们需要以与当前安装版本完全相同的方式来编译模块，以确保兼容性。

```bash
# 查看版本号，例如 nginx/1.18.0
nginx -v

# 查看完整的编译参数，并复制下来，后面会用到
nginx -V
```

**3. 下载 Nginx 源码并编译模块**

**注意事项**

- 编译时必须使用**完全相同的Nginx版本**源码

- ./configure`参数需与原始Nginx编译参数**完全一致**

- 生产环境建议使用**动态模块**方式编译：

```bash
# 根据上一步看到的版本号，下载对应的 Nginx 源码
# 假设版本是 1.24.0
wget http://nginx.org/download/nginx-1.24.0.tar.gz
tar -zxvf nginx-1.24.0.tar.gz
cd nginx-1.24.0/

# 运行 configure，粘贴上一步从 `nginx -V` 复制的所有参数，
# 并在末尾追加 --add-dynamic-module=/path/to/module
# ./configure [粘贴所有参数] --add-dynamic-module=/opt/ngx-fancyindex
# 示例:
# ./configure --prefix=/etc/nginx --sbin-path=/usr/sbin/nginx ... --add-dynamic-module=/opt/ngx-fancyindex

# 只编译模块，而不是整个 Nginx
make modules
```

**4. 加载模块**

编译成功后，会在 `objs` 目录下找到 `ngx_http_fancyindex_module.so` 文件。

```bash
# 将模块文件复制到 Nginx 的模块目录 (通常是 /etc/nginx/modules/)
sudo cp objs/ngx_http_fancyindex_module.so /etc/nginx/modules/

# 编辑主配置文件 /etc/nginx/nginx.conf
# sudo nano /etc/nginx/nginx.conf
```

在 `nginx.conf` 文件的最顶部，添加以下指令来加载模块：
```nginx
load_module modules/ngx_http_fancyindex_module.so;
```

**5. 验证**
最后，检查配置并重启 Nginx。
```bash
sudo nginx -t
#sudo systemctl restart nginx
sudo nginx -s reload
```
如果 Nginx 成功重启，说明模块已成功加载。现在，我们可以开始配置 `Nginxy` 主题了。

---
#### 1. 下载 `Nginxy` 主题到共享目录

这里的关键一步，是将主题文件下载到你**正在共享的目录**里面。根据我们之前的例子，这个目录是 `/data/shared-files`。我们把主题放在其中的一个隐藏目录 `.nginxy` 下。

```bash
# 进入你的文件共享目录
cd /data/shared-files

# 使用 git 克隆主题到当前目录下并把文件拷贝到 .nginxy 文件夹
#sudo git clone https://github.com/lfelipe1501/Nginxy.git 
# cp -a Nginxy/Nginxy-Theme .nginxy

wget https://github.com/lfelipe1501/Nginxy/releases/download/v2.1/nginxyV2.zip
unzip  nginxyV2.zip
```
> **提示**：目录名前的 `.` 使其成为一个隐藏目录，这样在文件列表中默认不会显示，更加整洁。

#### 2. 修改 Nginx 配置

现在，我们来更新 Nginx 配置。这个方案比之前的更简单。

```nginx
server {
    listen 15001; # 或者你使用的其他端口
    server_name your.server.ip.or.domain;

    location / {
        root /data/shared-files;   # 指定文件存放的根目录
        
        # fancyindex 相关配置
        fancyindex on;
        fancyindex_localtime on;
        fancyindex_exact_size off;
        fancyindex_header "/.nginxy/header.html"; # 引用主题头文件
        fancyindex_footer "/.nginxy/footer.html"; # 引用主题脚文件
        fancyindex_name_length 255;
        fancyindex_time_format "%d-%b-%Y %H:%M";
        
        # 可选：如果目录下有 index.html 则优先显示
        try_files $uri $uri/ /index.html;

        # Basic Auth 认证部分保持不变
        auth_basic "Restricted Area";
        auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

#### 3. 配置变更解释

这个配置之所以更简洁，是因为它巧妙地利用了 Nginx 的 `root` 指令。

1.  **不再需要独立的 `location` 块**：由于主题文件 (`.nginxy` 目录) 现在位于 `root` 目录 (`/data/shared-files`) 之内，Nginx 可以直接根据 URL 找到它们。
2.  **`fancyindex_header` 和 `fancyindex_footer` 的路径**：我们指定的路径是 `/.nginxy/header.html`。当请求到达时，Nginx 会将 `root` 路径与这个 URL 拼接，形成 `/data/shared-files/.nginxy/header.html` 的完整物理路径，从而准确地加载主题文件。
3.  **新增 `fancyindex` 指令**：
    *   `fancyindex_name_length 255`: 设置文件名显示的最大长度。
    *   `fancyindex_time_format "%d-%b-%Y %H:%M"`: 自定义文件修改时间的显示格式。
4.  **`try_files` 指令**：这是一个很有用的指令。它的意思是，当一个请求 (如 `/` 或 `/subdir/`) 到达时，Nginx 会按顺序尝试查找：
    *   `$uri`: 是否存在一个同名的文件。
    *   `$uri/`: 是否存在一个同名的目录（如果存在，则 `fancyindex` 会接管并显示目录内容）。
    *   `/index.html`: 如果前面都找不到，则尝试显示根目录下的 `index.html` 文件。这让你可以在需要时，通过在文件夹里放置一个 `index.html` 来提供一个说明页面，而不是直接显示文件列表。

#### 4. 重新加载 Nginx

最后，检查并重新加载 Nginx 配置使之生效。

```bash
sudo nginx -t && sudo nginx -s reload
```

现在，再次刷新页面，你就能看到焕然一新的 `Nginxy` 主题界面了！

---

### 总结

通过 Nginx，我们仅仅用了两个核心步骤：
1.  **配置 `location` 和 `autoindex`**，将 Nginx 变为一个文件服务器。
2.  **使用 `htpasswd` 创建密码文件，并配置 `auth_basic`**，为服务器加上访问控制。

这个方法不仅简单快捷，而且性能和稳定性都由身经百战的 Nginx 提供保障，非常适合用于内部文件分享、临时交付等场景。

希望这篇文章对你有帮助！如果你觉得有用，欢迎点赞、在看和分享。我们下期再见！
