## `deploy_local_jars.sh`
对于每一位Java开发者来说，Maven私服（Nexus/Artifactory）是项目管理的基石。但在某些场景下，填充私服却是一件极其痛苦的事。

### 让人头疼的使用场景

*   **首次搭建私有仓库**：公司决定搭建私服，如何将过去项目中积累的大量第三方、非公开的JAR包快速填充进去？
*   **项目迁移整合**：将一个非Maven管理的老项目迁移过来，它依赖的一堆本地JAR包需要统一上传到私服管理。
*   **离线环境部署**：在内网开发，需要先把外部下载的所有依赖包，一次性部署到内部私服中供团队使用。
*   **仓库数据恢复**：极端情况下私服数据损坏，但某个同事的本地仓库缓存最全，可以用此脚本从本地“反向同步”恢复数据。
如果手动一个一个执行 `mvn deploy:deploy-file`，输入长长的 GAV 参数，简直是“上刑”！

`deploy_local_jars.sh` 脚本，就是你的救星。它能自动扫描你本地Maven仓库的指定目录，解析 `pom.xml`，然后将所有相关的JAR包、POM文件（甚至包括 `sources.jar`, `javadoc.jar` 等）一键批量上传到你的私服！

#### 如何配置和使用 `deploy_local_jars.sh`

这个脚本在使用前，需要**修改顶部的3个配置变量**。

**1. 前提条件**
*   确保你安装了 `maven` 和 `xmllint`。
    *   在Ubuntu/Debian上安装 `xmllint`: `sudo apt-get install libxml2-utils`
    *   在CentOS/RHEL上安装 `xmllint`: `sudo yum install libxml2`
*   确保你的 `~/.m2/settings.xml` 文件中已经配置好了私服的认证信息（`<servers>` 标签）。脚本中的 `REPO_ID` 必须和 `settings.xml` 中的 `<server><id>` 匹配。

**2. 修改脚本配置**
打开 `deploy_local_jars.sh` 文件，找到顶部的配置区，修改以下三个变量：

```bash
# --- 请修改以下配置 ---

# 你的私有仓库的 URL (releases 或 snapshots)
# 【修改这里】=> 例如：https://nexus.mycompany.com/repository/my-releases/
REPO_URL="https://xxx.xxx.com/repository/third-party/"

# 你的私有仓库在 settings.xml 中配置的 <server> ID
# 【修改这里】=> 例如：my-nexus-releases
REPO_ID="third-party-releases"

# 要扫描的本地 Maven 仓库目录
# 【修改这里】=> 例如：/home/user/.m2/repository/com/aliyun
SOURCE_DIR="/home/zml/maven/repository/com/kjhxtc"

# --- 配置结束 ---
```

**3. 执行脚本**

*   给予执行权限：
    ```bash
    chmod +x deploy_local_jars.sh
    ```
*   运行脚本：
    ```bash
    ./deploy_local_jars.sh
    ```

之后，脚本就会自动开始扫描、解析和上传，你只需要静静地喝杯咖啡，看着屏幕上滚动的成功日志即可！
