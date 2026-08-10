# Shared, low-surprise helpers for everyone using the `liu` compute account.
# Keep this file free of project activation, credentials and destructive aliases.

export PATH="${HOME}/.local/bin:${PATH}"

alias gpu='watch -n 2 nvidia-smi'
alias gpuonce='nvidia-smi'
alias gpuproc='nvidia-smi pmon -c 1'
alias mem='free -h'
alias disk='df -h'
alias usage='ncdu /home/liu'
alias tasks='ps -u liu -o pid,etime,%cpu,%mem,cmd --sort=-%cpu'
alias envs='/home/liu/miniconda3/bin/conda env list'

compute-help() {
  printf '%s\n' \
    '公共算力机命令速查（再次查看：compute-help）' \
    '' \
    '[GPU]' \
    '  gpu                 持续查看 GPU 状态；按 Ctrl+C 退出' \
    '  gpuonce             查看一次 GPU、显存和占用进程' \
    '  gpuproc             查看一次 GPU 进程表' \
    '  nvtop               交互式 GPU 监控；按 q 退出' \
    '' \
    '[CPU / 内存 / 进程]' \
    '  btop                综合查看 CPU、内存、磁盘和进程；按 q 退出' \
    '  htop                交互式进程管理；按 q 退出' \
    '  mem                 查看内存与 Swap 使用量' \
    '  tasks               按 CPU 占用查看 liu 账号的进程' \
    '' \
    '[磁盘 / IO]' \
    '  disk                查看所有挂载盘容量' \
    '  duf                 更清晰地查看磁盘容量' \
    '  usage               交互式检查 /home/liu 空间；按 q 退出' \
    '  iostat -xz 2        每 2 秒查看磁盘 IO；按 Ctrl+C 退出' \
    '' \
    '[文件查找 / 阅读]' \
    '  rg 关键词 路径      在文件内容中搜索' \
    '  fd 文件名 路径      按文件名查找文件' \
    '  fzf                 交互式模糊筛选' \
    '  bat 文件            带高亮查看文本文件' \
    '  eza -lah            清晰列出目录内容' \
    '  tree -L 2           查看两层目录树' \
    '' \
    '[数据处理]' \
    "  jq '.字段' file.json       读取或转换 JSON" \
    "  yq '.字段' file.yaml       读取或转换 YAML" \
    '  mlr --csv stats1 file.csv  统计 CSV 列' \
    '  http GET URL               调试 HTTP/API 请求' \
    '' \
    '[传输 / 压缩]' \
    '  aria2c -x 8 URL            多连接下载文件' \
    '  rsync -ah --info=progress2 源 目标  增量复制目录' \
    '  pv 文件 > 目标             显示复制进度' \
    '  pigz -k 文件               多线程 gzip 压缩并保留原文件' \
    '  zstd -T0 -k 文件           多线程 zstd 压缩并保留原文件' \
    '' \
    '[任务 / 环境]' \
    '  tmux new -s 名称           创建可断线续跑的终端会话' \
    '  tmux attach -t 名称        重新进入已有会话' \
    '  parallel -j 4 命令 ::: 输入  最多并行 4 个任务' \
    "  hyperfine '命令'           测量命令运行时间" \
    '  entr                        文件变化后自动重跑命令' \
    '  envs                        查看所有 Conda 环境' \
    '  docker ps                   查看运行中的容器' \
    '' \
    '[Tim 私人工作台：其他组员无需使用]' \
    '  tim                 进入 Tim 的私人 zsh 工作台' \
    '  tim-bash            私人 Bash 回退工作台' \
    '  tim-doctor          检查私人工作台环境' \
    '' \
    '注意：不要删除他人文件；parallel 建议最多使用 -j 4。'
}
