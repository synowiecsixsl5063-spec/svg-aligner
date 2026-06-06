# svg-aligner

[![版本](https://img.shields.io/badge/版本-0.1.0-blue.svg)](https://github.com/synowiecsixsl5063-spec/svg-aligner)
[![许可证: MIT](https://img.shields.io/badge/许可证-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![零依赖](https://img.shields.io/badge/依赖-零-brightgreen.svg)](#安装)

[English](./README.md) | 中文 | [🌐 宣传页](https://synowiecsixsl5063-spec.github.io/svg-aligner)

> **面向 LLM 生成内容的确定性 SVG 坐标对齐后处理器。**

当 LLM 手写完整的 SVG XML 时（如在 [pptmaster](https://github.com/hugohe3/ppt-master) 中），视觉上应该对齐的元素经常出现像素级坐标偏移——一行本应左对齐的方框，坐标可能是 `x="120"`、`x="122"`、`x="119"`。**svg-aligner** 使用确定性算法检测这些"差一点对齐"的情况，并将其精确对齐，无需二次调用 LLM 即可生成干净、可预测的输出。

## 为什么需要 svg-aligner？

LLM **不是排版引擎**。当它们从零生成 SVG 时，产生的坐标只是*近似*正确的，通常会有 2–4 像素的漂移。这会导致：

- 文本框"糊在一起"，而不是整齐排列
- 列标题歪歪扭扭，无法形成整齐的一行
- 等间距布局在人眼看来"差一点"

svg-aligner 以确定性的方式修复这些问题——没有 AI 幻觉风险，没有 API 调用成本，每次结果都可预测。

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 左对齐漂移 | `x="120"`, `x="122"`, `x="119"` | `x="120"`, `x="120"`, `x="120"` |
| 不均匀分布 | 间距: 2px, 3px, 1px | 间距: 2px, 2px, 2px |
| 文本锚点混淆 | 文本视觉位置 194px vs 矩形 192px | 两者精确对齐到 192px |
| 嵌套变换漂移 | 深层元素与同级差 3px | 两者位于完全相同的位置 |

## 核心算法

对齐器分三个阶段工作：

1. **绝对坐标解析** — 遍历完整 SVG DOM 树，通过组合祖先 `transform` 矩阵，将每个叶子元素（rect、text、path 等）解析为根空间绝对包围盒。文本元素得到特殊处理：`text-anchor="middle"` 和 `"end"` 被计入视觉边缘计算，使对齐比较的是*你看到的*，而不是锚点坐标。

2. **基于极差的检测（5px 硬阈值）** — 对每种对齐维度（LEFT / RIGHT / TOP / BOTTOM / CENTER_H / CENTER_V / DISTRIBUTE_H / DISTRIBUTE_V），相关坐标落在**聚类窗口**（`阈值 × 3`）内的元素被分组。每组内计算该坐标的**极差**（max − min）。如果 `极差 < ALIGN_THRESHOLD`（默认 **5px**），该组被标记为需要修正。对于分布类型，算法改为检查**边缘间距**的极差。

3. **逆向 CTM 坐标回写** — 通过在绝对空间中计算偏移量，将其通过元素完整坐标变换矩阵的逆矩阵（`inv(parent_ctm × local_matrix)`）转换回去，并调整节点的本地属性（`x`、`y`、`cx`、`d` 等）。跨轴去重步骤确保每个元素最多只被一个水平和一个垂直修正触及，防止级联冲突。

## 安装

### 从源码安装

```bash
git clone https://github.com/synowiecsixsl5063-spec/svg-aligner.git
cd svg-aligner
pip install -e .
```

### 通过 pip 直接安装

```bash
pip install git+https://github.com/synowiecsixsl5063-spec/svg-aligner.git
```

### 免安装（独立使用）

svg-aligner **零外部依赖** —— 仅使用 Python 标准库。你可以直接将 `src/svg_aligner/core.py` 放入任何项目并导入使用。

## 快速开始

### CLI 模式

```bash
# 原地修正 SVG 文件
svg-aligner input.svg

# 写入新文件
svg-aligner input.svg -o corrected.svg

# 试运行：查看会修改什么，但不实际修改
svg-aligner input.svg --dry-run

# 自定义阈值（3px 而非默认的 5px）
svg-aligner input.svg --dry-run --threshold 3
```

### Python 模块

```python
from svg_aligner import process_svg

svg_string = open("input.svg").read()

# 试运行：检查计划的修正
out_svg, log = process_svg(svg_string, dry_run=True)
for action in log:
    print(f"{action['alignment_type']}: {len(action['affected_nodes'])} 个节点, "
          f"极差={action['range_px']:.1f}px")

# 实际应用修正
corrected_svg, log = process_svg(svg_string, dry_run=False)
open("output.svg", "w").write(corrected_svg)
```

### 自定义阈值

```python
from svg_aligner import process_svg

# 使用更严格的 3px 阈值
corrected_svg, log = process_svg(svg_string, threshold=3.0)
```

## 支持的元素类型

| 元素     | 被修改的属性                |
|----------|---------------------------|
| `rect`   | `x`, `y`                  |
| `circle` | `cx`, `cy`                |
| `ellipse`| `cx`, `cy`                |
| `line`   | `x1`, `y1`, `x2`, `y2`    |
| `text`   | `x`, `y`（锚点感知）        |
| `path`   | `d`（坐标平移）             |
| `polygon` / `polyline` | `points`     |
| 其他     | `transform`（回退前置）     |

## 测试

```bash
# 运行所有测试（需要 pytest）
pip install pytest
pytest tests/ -v

# 或使用内置 unittest 模块（无需额外依赖）
python -m unittest discover tests/ -v
```

测试套件覆盖：

- **嵌套变换** — `<g transform="translate(...)">` 内的元素正确解析为绝对坐标
- **文本锚点感知** — `middle` 和 `end` 锚点在回写时正确反转
- **等间距分布** — 近似均匀分布的元素精确对齐到等差数列
- **阈值保护** — 偏移 ≥ 5px 的元素完全不被触及
- **试运行模式** — 返回未修改的 SVG 同时生成操作日志
- **多页批处理** — 批量处理多个独立 SVG 字符串

## 多 AI 协作流程

svg-aligner 专为多 AI 协作工作流设计并经实战验证：

```
源文档 → 千问 (结构提取) → GPT (图像生成)
    → Claude Code (SVG 生成) → svg-aligner (坐标修正)
    → PPTX 导出
```

在 pptmaster 项目中，svg-aligner 作为 SVG 生成后的**最终质量关卡**：

1. **Claude Code** 生成带丰富布局的完整 SVG 幻灯片
2. **svg-aligner** 处理每张幻灯片，检测并修复像素级坐标漂移
3. 清理后的 SVG 被转换为原生可编辑的 PPTX

该流程经**300+ 页 SVG 地狱级压测**，涵盖多种文档类型（研究论文、产品发布、财务报告），已在生产环境中证明可靠。

### 与 pptmaster 集成

svg-aligner 已集成到 pptmaster 的 `finalize_svg` 后处理管线中。完整集成指南参见 [INTEGRATION.md](./INTEGRATION.md)。

## Bug 修复历史

svg-aligner 通过了**地狱级压力测试**，以下是关键修复：

| 修复编号 | 问题 | 解决方案 |
|---------|------|---------|
| **FIX-1** | ET 节点包装器双下划线方法冲突 | 显式 `__slots__` 和字符串拼接的双下划线名称 |
| **FIX-2** | SVG 序列化丢失命名空间声明 | 基于正则的 xmlns 检测与恢复 |
| **FIX-3** | 逆 CTM 仅使用父变换 | 完整 CTM = 父矩阵 × 本地矩阵，确保逆变换正确 |
| **FIX-4** | 回写时未考虑文本锚点 | 在 delta 计算前调用 `adjust_for_text_anchor()` |
| **FIX-5** | 畸形 XML 声明的解析问题 | 基于正则的声明剥离替代 `str.index()` |
| **FIX-6** | 深层嵌套 SVG 导致递归溢出 | `MAX_DOM_DEPTH = 512` 防护 DOM 遍历 |
| **FIX-7** | 命名空间前缀自动生成 | 预扫描并注册所有 xmlns 声明 |
| **FIX-8** | Path 元素坐标平移 | `_translate_path_d()` 直接修改 `d` 属性 |

## 故障排除与注意事项

### ⚠️ SVG 布局设计约束（面向 LLM Prompt 编写者）

生成将被 svg-aligner 处理的 SVG 时，请确保**不同列/行的元素在主对齐轴上至少间隔 20px**。

如果两列文本的 X 坐标在 5px 范围内（如 `x="48"`、`x="51"`、`x="52"`，都在 `y="244"`），对齐器会正确地将它们解释为"同一视觉行中有微小漂移的元素"，并将它们全部对齐到同一基线。这是算法**设计的预期行为**，而非 bug——它只是无法知道你想要创建独立的列。

**正确模式**：列之间保持足够间距：
```xml
<!-- 第 1 列：x=48 -->
<text x="48" y="244">第 1 列</text>
<!-- 第 2 列：x=340（292px 间距——安全地在 5px 窗口之外）-->
<text x="340" y="244">第 2 列</text>
<!-- 第 3 列：x=632（292px 间距）-->
<text x="632" y="244">第 3 列</text>
```

**需要对齐器修正的故意微小偏移**（2–4 px）应放在**同一列组内**：
```xml
<!-- 第 2 列内：标题/正文在 x=343/344——对齐器将对齐到 343 -->
<text x="343" y="244" font-weight="bold">标题</text>
<text x="344" y="274">正文</text>
```

### ⚠️ pptmaster 集成：清理中间文件

将 svg-aligner 集成到 **pptmaster** `finalize_svg` 管线时，下游的 `svg_to_pptx` 转换器会默认生成兼容性备份（`backup/<timestamp>/`）和中间目录（`svg_final/`、`svg_output/`）。

生成干净的仅含 `.pptx` 的输出：

```bash
# 使用 --only native 跳过 SVG 引用备份 PPTX
# 使用 -s final 从 svg_final/ 读取（后处理后的）
python scripts/svg_to_pptx.py <project_path> --only native -s final
```

或编程方式，在导出后调用 `cleanup_intermediates()` 删除 `svg_output/`、`svg_final/`、`backup/` 和 `.cache/` 目录。

## 项目结构

```
svg-aligner/
├── src/
│   └── svg_aligner/
│       ├── __init__.py          # 公共 API 导出
│       └── core.py              # 核心算法（零依赖）
├── tests/
│   ├── __init__.py
│   ├── test_unit.py             # 单元测试
│   └── test_integration.py      # 集成/压力测试
├── examples/
│   └── sample_usage.py          # 使用示例
├── README.md                    # 英文 README
├── README_CN.md                 # 中文 README（本文件）
├── INTEGRATION.md               # pptmaster 集成指南
├── LICENSE                      # MIT
├── .gitignore
└── pyproject.toml
```

## 许可证

MIT — 详见 [LICENSE](LICENSE)。
