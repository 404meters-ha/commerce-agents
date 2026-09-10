#!/usr/bin/env bash
# 停止 ./start.sh 起的全部进程: run_demo.py 会带走 uvicorn 和 Next.js;这里再兜底清理本仓库残留的子进程

cd "$(dirname "$0")" || exit 1

PATTERN="scripts/run_demo\.py (retail|travel|telecom|entertainment)"
PIDS="$(pgrep -f "${PATTERN}")"
if [ -z "${PIDS}" ]; then
    echo "commerce-agents 没有在运行"
    exit 0
fi

kill ${PIDS} 2>/dev/null
for _ in $(seq 1 10); do
    [ -z "$(pgrep -f "${PATTERN}")" ] && break
    sleep 1
done

pkill -TERM -f "app-dir $(pwd)/examples" 2>/dev/null
pkill -TERM -f "$(pwd)/examples/node_modules/.*next" 2>/dev/null
echo "[OK] commerce-agents 已停止 (日志在 /tmp/commerce-agents.log)"
