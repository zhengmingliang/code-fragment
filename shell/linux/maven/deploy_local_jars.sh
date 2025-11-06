#!/bin/bash

# ==============================================================================
# 脚本功能: 遍历本地 Maven 仓库的指定目录，解析 pom.xml 文件，
#           并将对应的 jar/pom 文件部署到私有 Maven 仓库。
#
# 版本: 2.0
# 更新日志:
#   - 增加了临时目录处理，以解决 Maven deploy 插件 "Cannot deploy artifact
#     from the local repository" 的错误。
#
# 使用方法:
#   1. 修改下面的配置变量。
#   2. 给予脚本执行权限: chmod +x deploy_local_jars.sh
#   3. 运行脚本: ./deploy_local_jars.sh
#
# 前提条件:
#   1. 必须安装 Maven (mvn 命令可用)。
#   2. 必须安装 xmllint (通常包含在 libxml2-utils 或类似包中)。
#   3. 你的 Maven settings.xml 文件 (~/.m2/settings.xml) 必须已配置好
#      私有仓库的认证信息。
# ==============================================================================

# --- 请修改以下配置 ---

# 你的私有仓库的 URL (releases 或 snapshots)
REPO_URL="https://maven.xxx.com/repository/third-party/"

# 你的私有仓库在 settings.xml 中配置的 <server> ID
REPO_ID="third-party-releases"

# 要扫描的本地 Maven 仓库目录
# 例如: /home/zml/maven/repository/com/bocsoft/berc
SOURCE_DIR="/home/zml/maven/repository/com/kjhxtc"

# --- 配置结束 ---


# --- 脚本主体 ---

# 函数: 检查命令是否存在
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# 函数: 从 pom 文件中提取信息
get_pom_value() {
  local pom_file="$1"
  local tag="$2"
  value=$(xmllint --xpath "string(//*[local-name()='project']/*[local-name()='$tag'])" "$pom_file" 2>/dev/null)
  if [[ -z "$value" && ("$tag" == "groupId" || "$tag" == "version") ]]; then
    value=$(xmllint --xpath "string(//*[local-name()='project']/*[local-name()='parent']/*[local-name()='$tag'])" "$pom_file" 2>/dev/null)
  fi
  echo "$value"
}

# 1. 检查依赖工具
echo "检查依赖工具..."
if ! command_exists mvn; then
  echo "错误: 'mvn' 命令未找到。请确保 Maven 已安装并在您的 PATH 中。"
  exit 1
fi
if ! command_exists xmllint; then
  echo "错误: 'xmllint' 命令未找到。请安装 libxml2-utils 或类似软件包。"
  exit 1
fi
echo "依赖检查通过。"

# 2. 检查源目录是否存在
if [ ! -d "$SOURCE_DIR" ]; then
  echo "错误: 源目录 '$SOURCE_DIR' 不存在。"
  exit 1
fi

# 3. 查找所有的 pom 文件并遍历
find "$SOURCE_DIR" -name "*.pom" | while read -r pom_file; do
  echo ""
  echo "========================================================================"
  echo "处理 POM 文件: $pom_file"
  
  # 创建一个唯一的临时目录用于本次上传
  TMP_DEPLOY_DIR=$(mktemp -d)
  if [ ! -d "$TMP_DEPLOY_DIR" ]; then
    echo "  [错误] 无法创建临时目录，跳过。"
    continue
  fi
  
  # 将 pom 文件复制到临时目录
  cp "$pom_file" "$TMP_DEPLOY_DIR"
  tmp_pom_file="$TMP_DEPLOY_DIR/$(basename "$pom_file")"

  # 提取 GAV 信息
  groupId=$(get_pom_value "$pom_file" "groupId")
  artifactId=$(get_pom_value "$pom_file" "artifactId")
  version=$(get_pom_value "$pom_file" "version")
  
  if [ -z "$groupId" ] || [ -z "$artifactId" ] || [ -z "$version" ]; then
    echo "  [警告] 无法从 '$pom_file' 中解析出完整的 GAV 信息，跳过此文件。"
    rm -rf "$TMP_DEPLOY_DIR" # 清理临时目录
    continue
  fi
  
  echo "  - 解析出的 GAV: ${groupId}:${artifactId}:${version}"
  
  dir=$(dirname "$pom_file")
  main_jar_file="${dir}/${artifactId}-${version}.jar"
  
  # 准备基础的 mvn deploy 命令，注意 -DpomFile 指向临时目录中的 pom
  base_cmd="mvn deploy:deploy-file -Durl=${REPO_URL} -DrepositoryId=${REPO_ID} -DgroupId=${groupId} -DartifactId=${artifactId} -Dversion=${version} -DpomFile=${tmp_pom_file}"
  
  # 4. 判断主 jar 文件是否存在，并执行部署
  if [ -f "$main_jar_file" ]; then
    echo "  - 发现主 JAR 文件: $main_jar_file"
    # 将 jar 文件也复制到临时目录
    cp "$main_jar_file" "$TMP_DEPLOY_DIR"
    tmp_jar_file="$TMP_DEPLOY_DIR/$(basename "$main_jar_file")"

    # 构建指向临时目录文件的部署命令
    deploy_cmd="${base_cmd} -Dfile=${tmp_jar_file} -Dpackaging=jar"
    
    echo "  - 正在执行上传命令..."
    if ! $deploy_cmd; then
      echo "  [错误] 上传 '${main_jar_file}' 失败！"
    else
      echo "  - 上传成功。"
    fi
  else
    echo "  - 未发现主 JAR 文件，将只上传 POM 文件。"
    deploy_cmd="${base_cmd} -Dfile=${tmp_pom_file} -Dpackaging=pom"
    
    echo "  - 正在执行上传命令..."
    if ! $deploy_cmd; then
      echo "  [错误] 上传 '${pom_file}' 失败！"
    else
      echo "  - 上传成功。"
    fi
  fi
  
  # 5. 查找并上传其他带有分类器（classifier）的 jar 包
  for extra_jar in "${dir}/${artifactId}-${version}-"*.jar; do
    if [ -f "$extra_jar" ]; then
      classifier_part=$(basename "$extra_jar" .jar)
      classifier=${classifier_part#${artifactId}-${version}-}
      
      echo "  - 发现带分类器的 JAR 文件: $extra_jar (classifier: $classifier)"
      
      # 复制带分类器的 jar 到临时目录
      cp "$extra_jar" "$TMP_DEPLOY_DIR"
      tmp_extra_jar="$TMP_DEPLOY_DIR/$(basename "$extra_jar")"
      
      # 构建指向临时目录文件的部署命令
      deploy_classifier_cmd="${base_cmd} -Dfile=${tmp_extra_jar} -Dclassifier=${classifier}"
      
      echo "  - 正在执行上传命令..."
      if ! $deploy_classifier_cmd; then
        echo "  [错误] 上传 '${extra_jar}' 失败！"
      else
        echo "  - 上传成功。"
      fi
    fi
  done

  # 清理本次循环创建的临时目录
  rm -rf "$TMP_DEPLOY_DIR"
  echo "  - 清理临时目录: $TMP_DEPLOY_DIR"
  
done

echo ""
echo "========================================================================"
echo "脚本执行完毕。"
