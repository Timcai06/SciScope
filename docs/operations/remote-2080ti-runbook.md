# 2080 Ti 远端手动运行手册

本手册只定义远端前置检查和人工启动顺序。任何数据导入、embedding、推荐模型构建都不会自动执行。

## 固定边界

- 远端仓库：`/home/liu/workspaces/sciscope/repo`
- Conda Python：`/home/liu/miniconda3/envs/sciscope/bin/python`
- PostgreSQL：本机 `127.0.0.1:5432`，数据库和角色均为 `sciscope`
- 旧 SciScope 语料继续作为全量 embedding 的输入；讯飞交付物走独立准入审计，不能直接替换旧语料。
- `/mnt/sda-inspect` 当前是只读检查挂载点，不作为运行目录。

## 第一次准备数据库

连接远端并进入仓库：

```bash
zjgsu2080
cd /home/liu/workspaces/sciscope/repo
```

安装并初始化 PostgreSQL 16 + pgvector。该命令需要人工输入 `sudo` 密码，但不会导入论文：

```bash
bash scripts/prepare_remote_runtime.sh
```

只读检查前置条件：

```bash
bash scripts/check_remote_readiness.sh
```

## 讯飞交付物校验

等待 `.aria2` 断点文件消失后，执行传输级完整性校验：

```bash
bash scripts/verify_xunfei_delivery.sh
```

该命令只检查文件大小、gzip 数据流并记录收到文件的 SHA-256；不会解压、解析、入库或 embedding。由于出题方未提供公开 checksum，生成的 SHA-256 只能作为本次收到制品的内部收据。

## 重任务的人工启动顺序

只有 `check_remote_readiness.sh` 中代码、GPU、模型、语料和数据库项通过后，才按顺序执行：

```bash
bash scripts/run_remote_pipeline.sh load --execute
bash scripts/check_remote_readiness.sh
bash scripts/run_remote_pipeline.sh embed --execute
bash scripts/run_remote_pipeline.sh recommend --execute
```

删除 `--execute` 时脚本会拒绝运行。不要并行启动这三个阶段。

若希望 embedding 在 SSH 断开后继续：

```bash
nohup bash scripts/run_remote_pipeline.sh embed --execute \
  > /home/liu/workspaces/sciscope/logs/embedding-launch.log 2>&1 &
echo $!
```

监控命令：

```bash
tail -f /home/liu/workspaces/sciscope/logs/embedding-launch.log
nvidia-smi
```

## 停止点

完成环境和资产检查并不等于 G03、E02 或任何国赛任务已经 `PASS`。正式状态只能在相应评测、人工标注或外部证据完成后更新。
