# GEM5 与 RTL 预取器计数器对照

本文档说明 `targets/prefetch.yaml` 中用于 GEM5/RTL 预取器对比的计数器、字段语义，以及 `accuracy` 和 `coverage` 的计算口径。文档针对当前 GCC15 SPEC06 数据处理流程；计数器名称以统计文件中的实际名称为准。

## 1. 统计段

GEM5 和 RTL 的计数器文件都包含两段统计结果：第一段是 warmup，第二段是正式运行。预取器对比只使用第二段。

- GEM5 解析最后一个正式统计块。
- RTL 对重复出现的同名统计项保留最后一次。
- 文件中应同时能看到 warmup 和 main 两段；如果只存在一段，需要检查输入结果是否完整。

因此，文档中的所有 issue/useful/unused/late 和 demand miss 都是正式运行段的值，不把 warmup 的计数累加进去。

## 2. 术语

| 术语 | 含义 |
| --- | --- |
| issue | 预取器发出一个预取请求的次数。GEM5 中对应 `pfIssued`，RTL 中通常对应 `Sent`。 |
| useful | 预取数据在被驱逐前被处理器需求命中、因此实际提供了数据的次数。GEM5 中对应 `pfUseful`，RTL 中对应 `Hit` 或 `Useful`。 |
| unused | 预取请求完成但从未被需求使用的次数。GEM5 有直接的 `pfUnused` 计数器；RTL 的 L2 没有该计数器，见第 4.3 节。 |
| late | 预取请求到达太晚，需求访问已经发生或未能及时隐藏缺失延迟的次数。该计数器不等同于 useful，也不应从 useful 中扣除。 |
| demand MSHR miss | 没有被已有缓存/预取请求覆盖、需要占用 demand MSHR 的需求缺失次数，是 coverage 分母中的需求缺失项。 |

## 3. L1 预取器

L1 只有 Stream 和 Stride 两个预取器。GEM5 的 source 可能以数字或枚举名称打印，解析器同时支持两种写法：Stream 为 source `1`/`SStream`，Stride 为 source `2`/`SStride`。

### 3.1 计数器映射

| 预取器/语义 | GEM5 | RTL |
| --- | --- | --- |
| Stream issue | `system.cpu.dcache.prefetcher.pfIssued_srcs::1` 或 `::SStream` | `l1prefetchSentStream` |
| Stream useful | `system.cpu.dcache.prefetcher.pfUseful_srcs::1` 或 `::SStream` | `l1prefetchHitStream` |
| Stream unused | `system.cpu.dcache.prefetcher.pfUnused_srcs::1` 或 `::SStream` | `l1prefetchUselessStream` |
| Stream late | `system.cpu.dcache.prefetcher.late_srcs::1` 或 `::SStream` | `l1prefetchLateStream` |
| Stride issue | `system.cpu.dcache.prefetcher.pfIssued_srcs::2` 或 `::SStride` | `l1prefetchSentStride` |
| Stride useful | `system.cpu.dcache.prefetcher.pfUseful_srcs::2` 或 `::SStride` | `l1prefetchHitStride` |
| Stride unused | `system.cpu.dcache.prefetcher.pfUnused_srcs::2` 或 `::SStride` | `l1prefetchUselessStride` |
| Stride late | `system.cpu.dcache.prefetcher.late_srcs::2` 或 `::SStride` | `l1prefetchLateStride` |

L1 demand MSHR miss：

- GEM5：`system.cpu.dcache.prefetcher.demandMshrMisses`
- RTL：DCache 的 `prefetcherMonitor` 中的 `mshr_count_CPU`。正则限定在 `dcache`/`dcache.dcache` 的 monitor，避免误取 L2 的同名项。

### 3.2 L1 accuracy 与 coverage

对任意 L1 预取器 `p`（`stream` 或 `stride`）：

```text
p_accuracy = p_useful / (p_useful + p_unused)
p_coverage = p_useful / (p_useful + l1_demand_mshr_miss)
```

L1 总体先聚合 Stream 和 Stride，再计算比例：

```text
l1_total_issued = l1_stream_issued + l1_stride_issued
l1_total_useful = l1_stream_useful + l1_stride_useful
l1_total_unused = l1_stream_unused + l1_stride_unused

l1_total_accuracy = l1_total_useful /
                    (l1_total_useful + l1_total_unused)
l1_total_coverage = l1_total_useful /
                    (l1_total_useful + l1_demand_mshr_miss)
```

## 4. L2 预取器

跨平台对比的 L2 预取器为 Stream、Stride、SMS 和 BOP。GEM5 的 SMS 统计源名称是 `SPht`，BOP 统计源名称是 `HWP_BOP`。CMC 只在 GEM5 中存在，因此不放入跨平台的 L2 total。

### 4.1 GEM5 计数器映射

GEM5 L2 计数器前缀为 `system.l2_wrappers.prefetcher`。每个预取器的四类计数器使用相同的 source 后缀：`pfIssued_srcs`、`pfUseful_srcs`、`pfUnused_srcs` 和 `late_srcs`。

| 预取器 | source 后缀 |
| --- | --- |
| Stream | `::1` 或 `::SStream` |
| Stride | `::2` 或 `::SStride` |
| SMS | `::3` 或 `::SPht` |
| BOP | `::4` 或 `::HWP_BOP` |
| CMC（GEM5-only） | `::CMC` |

例如，BOP issue/useful/unused/late 分别为：

```text
system.l2_wrappers.prefetcher.pfIssued_srcs::HWP_BOP
system.l2_wrappers.prefetcher.pfUseful_srcs::HWP_BOP
system.l2_wrappers.prefetcher.pfUnused_srcs::HWP_BOP
system.l2_wrappers.prefetcher.late_srcs::HWP_BOP
```

CMC 的对应项为相同四个字段加 `::CMC`。CMC 仍可输出 GEM5 专用的 `gem5_l2_cmc_accuracy_exact` 和 `gem5_l2_cmc_coverage`，但不参与公共 `l2_total_*`。

### 4.2 RTL 计数器映射

| 预取器/语义 | RTL |
| --- | --- |
| Stream issue/useful/late | `l2prefetchSentStream` / `l2prefetchUsefulStream`（或 `l2prefetchHitStream`） / `l2prefetchLateStream` |
| Stride issue/useful/late | `l2prefetchSentStride` / `l2prefetchUsefulStride`（或 `l2prefetchHitStride`） / `l2prefetchLateStride` |
| SMS issue/useful/late | `l2prefetchSentSMS` / `l2prefetchUsefulSMS`（或 `l2prefetchHitSMS`） / `l2prefetchLateSMS` |
| BOP issue/useful/late | `l2prefetchSentBOP + l2prefetchSentPBOP` / `l2prefetchUsefulBOP`（或 `HitBOP`）` + `l2prefetchUsefulPBOP`（或 `HitPBOP`） / `l2prefetchLateBOP + l2prefetchLatePBOP` |

RTL 没有 CMC 计数器。RTL 的 BOP 和 PBOP 都属于 GEM5 的 BOP source，抽取时先分别读取，再求和后与 GEM5 的 `HWP_BOP` 对比。

L2 demand MSHR miss：

- GEM5：`system.l2_wrappers.prefetcher.demandMshrMisses`
- RTL：`l2cache.topDown` 中的 `mshr_count_CPU`

限定 `l2cache.topDown` 很重要，因为 RTL 的 DCache monitor 也有名为 `mshr_count_CPU` 的计数器；后者只能用于 L1 coverage。

### 4.3 L2 unused 的近似

RTL 没有 L2 unused 计数器，因此公共 L2 accuracy 使用统一的近似口径：

```text
l2_p_unused ~= l2_p_issued - l2_p_useful - l2_p_late
l2_p_accuracy = l2_p_useful / (l2_p_useful + l2_p_unused)
```

其中 `p` 为 `stream`、`stride`、`sms` 或 `bop`。GEM5 仍保留直接读取的 `pfUnused`，并额外计算 `gem5_l2_<p>_accuracy_exact`，用于检查近似误差；公共 `l2_<p>_accuracy` 则和 RTL 使用同一口径。

### 4.4 L2 accuracy 与 coverage

对任意公共 L2 预取器 `p`：

```text
l2_p_accuracy = l2_p_useful / (l2_p_useful + l2_p_unused)
l2_p_coverage = l2_p_useful / (l2_p_useful + l2_demand_mshr_miss)
```

L2 总体只聚合 Stream、Stride、SMS、BOP：

```text
l2_total_issued = l2_stream_issued + l2_stride_issued +
                  l2_sms_issued + l2_bop_issued
l2_total_useful = l2_stream_useful + l2_stride_useful +
                   l2_sms_useful + l2_bop_useful
l2_total_unused = l2_stream_unused + l2_stride_unused +
                   l2_sms_unused + l2_bop_unused

l2_total_accuracy = l2_total_useful /
                    (l2_total_useful + l2_total_unused)
l2_total_coverage = l2_total_useful /
                    (l2_total_useful + l2_demand_mshr_miss)
```

CMC 不计入上述 total；如果只分析 GEM5，可单独使用：

```text
gem5_l2_cmc_accuracy_exact = gem5_l2_cmc_useful /
                             (gem5_l2_cmc_useful + gem5_l2_cmc_unused_exact)
gem5_l2_cmc_coverage = gem5_l2_cmc_useful /
                        (gem5_l2_cmc_useful + l2_demand_mshr_miss)
```

## 5. 缺失值、零分母和加权

- GEM5 常常省略值为零的 source breakdown。对于已知的 GEM5 L1/L2 预取器 source counter，缺失按 `0` 处理。
- RTL 缺失统计项不能普遍按零处理，保留为 `NaN`，以区分“确实为零”和“没有找到计数器”。
- 分母为零时比例保留为 `NaN`。导出或比较界面显示为 `N/A`，不会把整个 benchmark 或表项强制变成无效。
- SimPoint 加权时先对原始 counter 做加权求和，再用加权后的 useful/unused/demand miss 重新计算 accuracy 和 coverage。不能直接对各 SimPoint 的比例做简单平均，否则某个点的 `0/0` 会污染结果。

## 6. CSV 输出

完整抽取使用 `prefetch` domain：

```bash
python3 batch.py -s <结果目录> --groups l1_prefetch,l2_prefetch -o results/prefetch.csv
```

SimPoint 加权必须使用包含原始 counter 的完整 CSV，确保 accuracy/coverage
能够从加权后的 counter 重新计算：

```bash
python3 -m simpoint_cpt.compute_weighted \
    -r results/gem5-prefetch.csv \
    -j simpoint_cpt/resources/<weights.json> \
    -o results/gem5-prefetch-weighted.csv
python3 -m simpoint_cpt.compute_weighted \
    -r results/rtl-prefetch.csv \
    -j simpoint_cpt/resources/<weights.json> \
    -o results/rtl-prefetch-weighted.csv
```

加权完成后，再只保留 accuracy/coverage 的公共字段：

```bash
python3 filter_prefetch_metrics.py results/gem5-prefetch-weighted.csv \
    results/gem5-prefetch-ac-cov.csv --platform gem5
python3 filter_prefetch_metrics.py results/rtl-prefetch-weighted.csv \
    results/rtl-prefetch-ac-cov.csv --platform rtl
```

公共精简字段为：

```text
l1_stream_accuracy, l1_stream_coverage
l1_stride_accuracy, l1_stride_coverage
l1_total_accuracy, l1_total_coverage
l2_stream_accuracy, l2_stream_coverage
l2_stride_accuracy, l2_stride_coverage
l2_sms_accuracy, l2_sms_coverage
l2_bop_accuracy, l2_bop_coverage
l2_total_accuracy, l2_total_coverage
```

GEM5 文件还可包含 `gem5_l2_cmc_accuracy_exact` 和 `gem5_l2_cmc_coverage`
两个 GEM5-only 字段。比较结果时，两个输入文件应使用相同的 benchmark
标识；缺少某个平台数据的指标显示为 `N/A`，这是数据缺失或零分母的明确提示。
