#!/usr/bin/env bash
# 傻瓜式启动(服务器用): ./start.sh [retail|travel|telecom|entertainment] [--merchant|--all]
# 对外服务: 自动探测公网 IP 传给 run_demo.py --public-host; 用 PUBLIC_HOST=1.2.3.4 ./start.sh 可覆盖。
# 凭据只认 .env 里的 DEEPSEEK_API_KEY; shell 里残留的 ANTHROPIC_* 会被清除,请求只走 DeepSeek。
# 停止: ./stop.sh   日志: /tmp/commerce-agents.log

cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
    echo "[ERROR] 缺少 .venv。先执行:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && (cd examples && npm ci)"
    exit 1
fi

# .env 提供凭据(run_demo.py 也会自己读一遍;这里 source 是为了 key 校验和子进程环境)
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "[ERROR] 没有配置 DEEPSEEK_API_KEY。执行: cp .env.example .env 填入 key 后重试。"
    exit 1
fi

VERTICAL="${1:-retail}"
if [ "$#" -gt 0 ]; then shift; fi

# 对外地址(浏览器从哪里访问页面就填哪个): PUBLIC_HOST(.env 或环境) > 阿里云元数据
# 的 eipv4 / public-ipv4 > 都没有则按本机模式启动。私网地址不算数——它出现在页面里,
# 外部浏览器照样连不上 API。
is_public_ip() {
    case "$1" in
        10.*|127.*|169.254.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) return 1 ;;
    esac
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

PUBLIC_HOST="${PUBLIC_HOST:-}"
if [ -n "$PUBLIC_HOST" ] && ! is_public_ip "$PUBLIC_HOST"; then
    echo "[WARN] PUBLIC_HOST=$PUBLIC_HOST 不是公网 IPv4,仍然按它启动(显式指定的优先)"
fi
if [ -z "$PUBLIC_HOST" ]; then
    for FIELD in eipv4 public-ipv4; do
        CANDIDATE="$(curl -fsS --max-time 2 "http://100.100.100.200/latest/meta-data/${FIELD}" 2>/dev/null | tr -d '[:space:]')"
        if is_public_ip "$CANDIDATE"; then
            PUBLIC_HOST="$CANDIDATE"
            break
        fi
    done
fi

if pgrep -f "scripts/run_demo\.py ${VERTICAL}" > /dev/null 2>&1; then
    echo "[WARN] commerce-agents (${VERTICAL}) 已在运行,请先执行 ./stop.sh 停止"
    exit 1
fi

# run_demo.py 自己补装缺失依赖、起 API 和 web、搬开被占用的端口;
# --public-host 让 API 绑 0.0.0.0、放行该主机的 Host 头和 web 源,并把 web 应用指向它
PUBLIC_ARGS=""
if [ -n "$PUBLIC_HOST" ]; then
    PUBLIC_ARGS="--public-host ${PUBLIC_HOST}"
    echo "[INFO] 对外地址: ${PUBLIC_HOST}"
else
    echo "[WARN] 未探测到公网地址,按本机模式启动,外部页面的 chat 连不上 API。"
    echo "       修复: 在 .env 里加一行 PUBLIC_HOST=<服务器公网IP>,再执行 ./stop.sh && ./start.sh"
fi
nohup .venv/bin/python scripts/run_demo.py "${VERTICAL}" ${PUBLIC_ARGS} "$@" \
    > /tmp/commerce-agents.log 2>&1 &

API_PORT=8000
case "$VERTICAL" in
    travel) API_PORT=8001 ;;
    telecom) API_PORT=8002 ;;
    entertainment) API_PORT=8003 ;;
esac
WEB_PORT=$((API_PORT - 5000))

# 等就绪:进程退出即报错,health 接口通了即成功(至多 90 秒)
for _ in $(seq 1 90); do
    if ! pgrep -f "scripts/run_demo\.py ${VERTICAL}" > /dev/null 2>&1; then
        echo "[ERROR] 启动失败,最近日志:"
        tail -20 /tmp/commerce-agents.log
        exit 1
    fi
    if curl -fsS "http://localhost:${API_PORT}/api/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -fsS "http://localhost:${API_PORT}/api/health" > /dev/null 2>&1; then
    echo "[ERROR] 90 秒内未就绪,最近日志:"
    tail -20 /tmp/commerce-agents.log
    exit 1
fi

HOST_SHOW="${PUBLIC_HOST:-localhost}"
echo "[OK] commerce-agents (${VERTICAL}) 已启动"
echo "     Storefront: http://${HOST_SHOW}:${WEB_PORT}"
echo "     API Health: http://${HOST_SHOW}:${API_PORT}/api/health"
echo "     实时日志:   tail -f /tmp/commerce-agents.log"
echo "     提醒: 云服务器需在安全组放行 TCP ${WEB_PORT} 和 ${API_PORT} 才能从外部访问"
