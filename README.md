# 启衡计量室换机复核台账

启衡计量室白班接收校验台的两机同步扫描记录。夜班在旧机和站库停源后，根据手中的确切发行件换算替代机复测基准。次班班长凭原报告号核对已采用的基准及其出处。

## 一天的交接

1. 白班计量员将台架原测段及其出处按原序登记成批修订。
2. 发行员指定批和修订，冻结一份 V1 固定件。
3. 夜班接件员按预期发行身份实收固定件，留存首收凭据。同件重投领取同一凭据。
4. 站库停源后，分析员选定实收号并申报旧机刻度。
5. 中心核定替代机基准，将报告和首执一起签存。次班据数值安排复测，或据无证据结论转人工处理。
6. 白班收到勘误时登记独立修订，当前指针随登记提交移动。
7. 发行员和夜班以更正版重复交接与核定，形成绑定新父件的报告。
8. 次日重开后，班长按各自报告号领取原定稿、原父件和原首执。

## Python 接口

使用 Python 3.11 标准库。调用者用 `sqlite3.connect` 分别打开站库和中心库，在空闲连接上初始化。站库依次调用 `RevisionStore(station).initialize()`、`IssueStore(station).initialize()`。中心库依次调用 `ReceiptStore(center).initialize()`、`ReportStore(center).initialize()`。存储类位于同名职责目录的 `*_store.py`。每次重开均可重复初始化。原修订、当前指针、发行、实收和报告继续可用。业务写入口各自管理事务，调用时连接须没有外层事务。并发调用使用各自的 SQLite 连接。

| 入口 | 参数及成功结果 |
| --- | --- |
| `station.import_batch.register` | `(station, batch_id, revision_id, rows)` 返回登记的 `BatchRevision`。通过 `RevisionStore.get_current(batch_id)` 查询当前修订，通过 `get_revision(RevisionKey(...))` 查确切原版。非法行、空批和覆盖已有修订返回 `RegistrationError`。 |
| `issue.issue.issue` | `(station, batch_id, revision_id)` 返回 `IssuedPackage(identity, package_text)`。确切修订缺失返回 `RevisionNotFound`。同版重复调用返回原发行号和原冻结文本。 |
| `receipt.intake.receive` | `(center, package_text, expected_identity)` 返回 `IntakeAcknowledgment(receipt_id, confirmation)`。`expected_identity` 由交接人从交接指令取得，包含发行号、批和修订。错件、坏件和发行号冲突返回 `ReceiptRejected`。 |
| `analysis.request.review` | `(center, receipt_id, tick)` 返回 `ReviewPublication`，含定稿及原首执。未知实收号或非法刻度返回 `ReviewRequestError`，签存失败返回 `SignStorageError`。 |
| `report.readback.read` | `(center, report_id)` 返回 `ReportReadback`，含已存定稿、精确父件及原首执。未知编号返回 `ReportNotFound`。 |

输入身份为首尾无空白的非空可打印字符串。登记行字段为 `x0`、`x1`、`y0`、`y1`、`weight` 和 `source`。`source` 含 `record`、`scan_start`、`scan_end`。台架原序与原出处保存在站库。Python 有理输入接收 `Fraction`、整数或可由 Python 3.11 `Fraction` 精确解析的字符串，例如 `"-2"`、`"7/8"` 和 `"0.25"`。零端点和零刻度合法，段权重必须严格为正。浮点值、布尔值和缺失值会被拒绝。两轴使用各自的固定仪器刻度，报告数值使用替代机刻度。

V1 固定件是 JSON 文本，外层字段为 `version`、`issue_id`、`batch_id`、`revision_id`、`body`。正文 `joint_segments` 是非空数组，其中每段有 `x0`、`x1`、`y0`、`y1`、`weight` 五个有理字段。发行使用有理字符串。共同参数均匀遍历 `[0,1]`，`(x0,y0)` 和 `(x1,y1)` 分别是同次公开端点。公开质量可合并方向与端点完全相同的段的权重。原行、原序及私有扫描坐标留站。固定件以原文本交接和保存。已实收发行号收到不同文本时按冲突拒收。`samples/high-joint-v1.json` 是独立可实收的公开样例。

## 核定口径

每个正容差 `ε` 使用旧机闭窗 `[x−ε,x+ε]`。段内选中参数长度乘段权重给出窗内质量，再投到替代机轴。同读值的点质量及重合的连续贡献相加。累计质量首次达到总质量一半的位置是该窗的下中位数。签发该位置从正侧趋零的精确有理极限。结果状态为 `numeric` 或 `no_evidence`。`numeric` 的 `value` 是 `Fraction`，可以为零。`no_evidence` 的 `value` 是 `None`。输入和结果均可重复核对，计算没有浮点近似或随机种子。

## 运行

```sh
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 由运行平台提供，运行 `tests` 包内完整回归。测试覆盖含非法勘误与错件的冻结交接、独立联合件、停止使用站库后的双件核定、连续边界、恒定与重合质量、未知父件、真实 SQLite 写失败回滚和重开历史。测试及演示只在临时目录建库。演示用两份同边缘配对修订核定并重开领取，初版为 2，勘误版为 0，两个报告分别保有自己的原父件和首执。
