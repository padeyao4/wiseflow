#!/bin/bash

# 1. 检查 pocketbase 是否存在
check_pocketbase() {
    if [ -f "./pb/pocketbase" ]; then
        echo "检测到 ./pb/pocketbase 已经存在，请手动删除并重试"
        exit 1
    fi
    
    # 如果目录不存在，则创建目录
    if [ ! -d "./pb" ]; then
        mkdir -p ./pb
    fi
}

# 2. 获取可用版本
get_versions() {
    echo "正在获取可用版本..."
    VERSIONS=($(curl -s https://api.github.com/repos/pocketbase/pocketbase/releases | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/'))
    LATEST_VERSION=${VERSIONS[0]}
}

# 3. 使用箭头键选择版本
select_version() {
    # 清屏
    clear
    
    # 存储版本的数组
    local versions=("${VERSIONS[@]}")
    local current=0
    local key
    local total=${#versions[@]}
    
    while true; do
        # 清屏
        clear
        echo "可用版本（使用 ↑↓ 箭头选择，按 Enter 确认）："
        echo "----------------------------------------"
        
        # 显示版本
        for i in "${!versions[@]}"; do
            if [ $i -eq $current ]; then
                echo -e "\033[32m-> ${versions[$i]}\033[0m"
            else
                echo "   ${versions[$i]}"
            fi
        done
        
        # 读取一个字符
        read -rsn1 key
        
        # 特殊键序列
        if [[ $key = $'\x1b' ]]; then
            read -rsn2 key
            case $key in
                '[A') # 上箭头
                    ((current--))
                    [ $current -lt 0 ] && current=$((total - 1))
                    ;;
                '[B') # 下箭头
                    ((current++))
                    [ $current -ge $total ] && current=0
                    ;;
            esac
        elif [[ $key = "" ]]; then # Enter 键
            SELECTED_VERSION=${versions[$current]}
            break
        fi
    done
    
    echo -e "\n选择的版本: $SELECTED_VERSION"
}

# 4. 下载对应系统版本
download_pocketbase() {
    # 检测操作系统和架构
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    
    # 从版本号中移除 'v' 前缀
    VERSION_NUM=${SELECTED_VERSION#v}
    
    case "$OS" in
        "darwin") 
            case "$ARCH" in
                "x86_64") FILENAME="pocketbase_${VERSION_NUM}_darwin_amd64.zip" ;;
                "arm64") FILENAME="pocketbase_${VERSION_NUM}_darwin_arm64.zip" ;;
            esac
            ;;
        "linux")
            case "$ARCH" in
                "x86_64") FILENAME="pocketbase_${VERSION_NUM}_linux_amd64.zip" ;;
                "aarch64") FILENAME="pocketbase_${VERSION_NUM}_linux_arm64.zip" ;;
            esac
            ;;
        *)
            echo "不支持的操作系统"
            exit 1
            ;;
    esac

    # 下载并解压
    DOWNLOAD_URL="https://github.com/pocketbase/pocketbase/releases/download/${SELECTED_VERSION}/${FILENAME}"
    echo "正在下载: $DOWNLOAD_URL"
    
    # 带重试机制的下载
    MAX_RETRIES=3
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -L "$DOWNLOAD_URL" -o "./pb/${FILENAME}" --fail --silent --show-error; then
            if [ -f "./pb/${FILENAME}" ] && [ -s "./pb/${FILENAME}" ]; then
                echo "下载成功"
                break
            fi
        fi
        
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "下载失败，正在重试 ($RETRY_COUNT/$MAX_RETRIES)..."
            sleep 2
        else
            echo "经过 $MAX_RETRIES 次尝试后下载失败"
            exit 1
        fi
    done
    
    # 仅提取 pocketbase 可执行文件
    cd ./pb || exit 1
    
    if ! unzip -j -o "${FILENAME}" "pocketbase" > /dev/null 2>&1; then
        echo "提取 pocketbase 可执行文件失败"
        cd ..
        exit 1
    fi
    
    rm "${FILENAME}"  # 删除 zip 文件
    
    if [ ! -f "pocketbase" ]; then
        echo "提取后未找到 pocketbase 可执行文件"
        cd ..
        exit 1
    fi
    
    chmod +x pocketbase
    cd ..
    
    echo "成功安装 pocketbase"
}

# 验证电子邮件格式
validate_email() {
    local email=$1
    if [[ ! "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        return 1
    fi
    return 0
}

# 验证密码要求
validate_password() {
    local password=$1
    # 检查最小长度为 8 个字符
    if [ ${#password} -lt 8 ]; then
        return 1
    fi
    return 0
}

# 5. 配置管理员账户
configure_admin() {
    local valid_input=false
    
    while [ "$valid_input" = false ]; do
        # 获取电子邮件
        while true; do
            echo "请设置超级用户电子邮件:"
            read EMAIL
            
            if validate_email "$EMAIL"; then
                break
            else
                echo "电子邮件格式无效。请重试。"
            fi
        done
        
        # 获取密码
        while true; do
            echo "请设置超级用户密码（至少 8 个字符）："
            read -s PASSWORD
            echo
            
            if validate_password "$PASSWORD"; then
                # 确认密码
                echo "请确认密码："
                read -s PASSWORD_CONFIRM
                echo
                
                if [ "$PASSWORD" = "$PASSWORD_CONFIRM" ]; then
                    valid_input=true
                    break
                else
                    echo "密码不匹配。请重试。"
                fi
            else
                echo "密码必须至少 8 个字符。请重试。"
            fi
        done
    done

    cd ./pb
    ./pocketbase migrate up
    
    # 尝试创建超级用户
    if ! ./pocketbase --dev superuser create "$EMAIL" "$PASSWORD"; then
        echo "创建超级用户失败。请检查上面的错误信息。"
        exit 1
    fi
    cd ..
    
    echo "超级用户创建成功！"
}

# 6. 配置环境文件
configure_env() {
    # 如果 .env 文件不存在，则创建
    if [ ! -f "./core/.env" ]; then
        # mkdir -p ./core
        cp env_sample ./core/.env
        echo "从模板创建新的 .env 文件"
    else
        echo "找到现有的 .env 文件"
    fi
    
    # 使用 sed 更新环境文件中的认证信息
    if [ "$(uname)" = "Darwin" ]; then
        # macOS 版本
        sed -i '' 's/export PB_API_AUTH="[^"]*"/export PB_API_AUTH="'$EMAIL'|'$PASSWORD'"/' "./core/.env"
    else
        # Linux 版本
        sed -i 's/export PB_API_AUTH="[^"]*"/export PB_API_AUTH="'$EMAIL'|'$PASSWORD'"/' "./core/.env"
    fi
    
    echo "在 .env 中更新了 PB_API_AUTH 的新凭据"
}

main() {
    echo "开始 PocketBase 安装..."
    check_pocketbase
    get_versions
    select_version
    download_pocketbase
    configure_admin
    configure_env
    echo "PocketBase 安装完成！"
}

main