# 双批混配签报

夜班选定甲乙两份校验批的实收件。签报列出在同一旧机刻度上可使替代机基准落入申报范围的全部配方比例。次班凭报告号领回原定稿，甲占比始终对应当时指定的甲件。

## 业务口径

沿用 README.md 的站库、中心库初始化方式和 V1 固定件格式。中心库中的 V1 件沿用同一对仪器的固定刻度口径。混配选件必须是两个不同 `batch_id` 的已实收 V1 件，甲乙有序。每件按全件总质量分别归一，再按甲 `p`、乙 `1−p` 合成联合质量。即使配方端点只用一件，报告仍绑定指定的两份实收件。

`tick` 是旧机刻度。`lo` 和 `hi` 是替代机读值的闭目标，允许 `lo == hi`。三者均用 README.md 所列 V1 精确有理输入。在 [0,1] 内每个有理比例上，对每个正容差 ε 沿用旧机闭窗 `[tick−ε,tick+ε]` 及 V1 下中位数定义。取该中位数随 ε 从正侧趋零的极限。充分小的窗内无质量时，该比例无证据。极限等于闭目标任一端时合格。结果按比例升序给出最大区间，端点为精确有理数，并保留端点开闭。孤点用两个相等的闭端点表示，空集也签存。

## Python 调用

- `analysis.request.sign_mix(center, left_receipt_id, right_receipt_id, tick, lo, hi)` 返回含 `.report` 和 `.acknowledgment` 的签发对象。
- `report.readback.read_mix(center, report_id)` 返回含 `.report`、`.acknowledgment` 和 `.parents` 的领取对象。`.parents` 是按甲乙排列的两个 `ReceiptRecord`，含实收原文 `.package_text` 和原实收凭据。
- 两个入口的 `.report` 均含 `.report_id`、有序整数对 `.receipt_ids`、`Fraction` 类型的 `.tick`、`.lo`、`.hi`，以及 `.intervals`。`.intervals` 是区间元组，区间项有 `Fraction` 类型的 `.lo`、`.hi` 和布尔类型的 `.lo_closed`、`.hi_closed`。空结果是空元组。签发首执 `.acknowledgment` 含 `.report_id` 和 `.confirmation`。

报告、归一申请、实际双件引用、结果与签发首执同次提交。连接须空闲，初始化仍由 `ReceiptStore(center).initialize()` 和 `ReportStore(center).initialize()` 完成。写失败无本次新增，可重新调用。勘误或重开后，领取返回原先签存的报告值、两份原实收正文和首执。原单件业务继续走原调用。

非法刻度或界值、倒置目标、非法或未知实收号、同批两件、无法验证的存档原件均抛出 `ReviewRequestError`。写入报告或首执失败抛出 `SignStorageError`。找不到指定混配定稿时，`read_mix` 抛出 `ReportNotFound`。异常类型沿用 V1 所在模块。

## 样例与运行

`samples/mix-scans.json` 是可从站库正常登记、冻结并实收的甲乙原始输入。`python3 -B mix_inputs.py` 试收这两份件，停用站库后分别显示 V1 单件基准 0 和 2。用这两件申报 `tick=0, lo=0, hi=0`，混配签报应含且仅含 `(1/2,1]`。交换两件应签 `[0,1/2)`。两份不同批次若各只有一条旧机恒为 0、替代机均匀扫过 [−1,1] 的线段，同一申报应签 `[0,1]`。

现有 `.pointwise-runtime.json` 使用 `version` 1、`kind` 为 `cli`，`setup` 是命令参数数组的列表，`verify` 和 `demo` 各为一条命令的参数数组。原回归为 `python3 -B check_project.py`，原单件交接演示为 `python3 -B demo.py`。交付时，`verify` 实际核对原回归与混配业务，`demo` 展示站库停用后的混配签发，以及重开中心后凭原号领取比例与双件出处。核验失败须返回非零退出码。
