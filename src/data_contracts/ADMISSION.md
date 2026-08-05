# 受控摄取数据字典（D01）

> 对应实现：`src/data_contracts/admission.py`
> 上游口径：`docs/plan/active/D00-数据准入清单.md` §7「讯飞数据最小元数据」
> 状态：D01 产物；2026-08 已按评审修订双哈希语义与类型校验，验收待项目负责人复核

本字典定义「新增论文进入 canonical / 运行库之前」的准入字段、值域与拒绝规则。
字段名即 JSON/JSONL 记录键名。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `paper_id` | str | 是 | 稳定 ID，跨版本可识别；字符集 `[A-Za-z0-9._:\-]`，长度 1–128 |
| `source` | str | 是 | 来源标识（如 `arxiv`、`pmc` 或讯飞语料标识）；**缺失即拒绝** |
| `license` | str | 是 | 许可标识（如 `cc0`、`cc-by`）；空或 `unknown`/`n/a` 视为许可未知，**拒绝** |
| `source_file_sha256` | str | 是 | **原始交付文件字节哈希**（sha256 hex，64 位小写）；本模块仅格式校验，内容一致性由 D02 摄取时回链核验 |
| `record_sha256` | str | 是 | **规范化记录哈希**；与记录内容哈希不一致**拒绝**（哈希不符样例） |
| `language` | str | 是 | 语言标识（如 `zh`、`en`）；缺失即拒绝 |
| `year` | int \| str | 是 | 发表年份；可解析为整数，否则拒绝 |
| `usage_rights` | str | 是 | 三权限分级：`indexable` / `snippet` / `redistributable` |
| `retracted` | bool | 否 | 撤稿标记；**存在时必须为布尔值**，否则拒绝 |
| `correction` | str | 否 | 更正说明；**存在时必须为字符串**（`null` 亦拒绝），否则拒绝 |

其余字段（标题、摘要、作者、全文等正文载荷）由上层记录携带，本合同不校验其内容，
但 `record_sha256` 计算时**排除**两个哈希字段自身与 `_sciscope_*` 前缀的治理元数据。

## 双哈希语义（2026-08 按评审修订）

- `source_file_sha256` = 原始论文/PDF **交付文件字节**的 sha256。它回答「这份数据来自哪个原始文件、
  能否回链」；真实讯飞数据至少要能回链到它。本模块没有原始文件字节，故只做格式校验
  （64 位 hex），内容一致性在 D02 摄取阶段核验。
- `record_sha256` = 对**规范化后的 JSON 记录**（排除两个哈希字段与 `_sciscope_*`）计算的 sha256。
  它回答「这条记录内容有没有被改过」；缺失、非 hex 或与内容不一致即拒绝。

## 值域

| 集合 | 值 | 用途 |
|---|---|---|
| `USAGE_RIGHTS` | `indexable`、`snippet`、`redistributable` | 三权限分级（D00 §6） |
| `REDISTRIBUTABLE_LICENSES` | `cc0`、`pd`、`public-domain` | `usage_rights=redistributable` 时 license 必须在此集合，否则拒绝 |

`license` 已知性判断：非空且不属于 `{unknown, n/a, na}`（大小写不敏感）即视为已知；
**未知许可一律拒绝入库**，更不得进入公开导出（D00 验收线）。

## 拒绝规则（顺序）

1. `paper_id` 缺失 / 为空 / 含非法字符；
2. `source` 缺失或为空；
3. `license` 缺失、为空或为 `unknown`（许可未知样例）；
4. `source_file_sha256` 缺失或非 64 位 hex（原始文件字节哈希，仅格式校验）；
5. `record_sha256` 缺失、非 64 位 hex、或与规范化记录哈希不一致（哈希不符样例）；
6. `language` 缺失或为空；
7. `year` 缺失或不可解析为整数；
8. `usage_rights` 缺失或不在三权限集合；
9. `usage_rights=redistributable` 但 `license` 不在可再分发集合；
10. `retracted` 存在但不是布尔值；
11. `correction` 存在但不是字符串。

拒绝不抛异常：`ingest_record` 返回 `IngestDecision(accepted=False, rejections=[...])`，
并把原因写入 `<受控目录>/rejections.jsonl`（每条含时间戳、记录摘要与逐字段原因）。

## 哈希算法

```python
compute_record_hash(record):
    payload = {k: v for k, v in record.items()
               if k not in {"source_file_sha256", "record_sha256"}
               and not k.startswith("_sciscope_")}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()
```

## 导入落点

通过合同的记录写入 `<staged_dir>/staged.jsonl`（默认 `data/admission/staged.jsonl`），
附加 `_sciscope_admission_schema=ingest-contract/v1` 与 `_sciscope_admitted_at` 时间戳；
该目录即 D00 清单 §7「受控原始区」，D02 从此处读取进行解析与切片。

## 验收样例

- 合法：`paper_id=PX-001, source=iflytek, license=cc0, source_file_sha256=<源文件字节哈希>,
  record_sha256=<内容哈希>, language=zh, year=2024, usage_rights=indexable` → 通过并导入
- 非法 1（缺来源）：`source` 缺失 → 拒绝 `source: missing_or_empty`
- 非法 2（哈希不符）：`record_sha256` 与内容不一致 → 拒绝 `record_sha256: hash_mismatch`
- 非法 3（许可未知）：`license="unknown"` → 拒绝 `license: unknown_license`
- 类型校验：`retracted="yes"` → 拒绝 `retracted: not_boolean`；`correction=123` → 拒绝
  `correction: not_string`
