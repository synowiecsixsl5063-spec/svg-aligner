# Social Media Promotional Kit — svg-aligner

## Quick Reference

- **Project**: svg-aligner — Deterministic SVG Alignment Post-Processor
- **GitHub**: https://github.com/synowiecsixsl5063-spec/svg-aligner
- **Landing Page**: https://synowiecsixsl5063-spec.github.io/svg-aligner
- **Tagline**: "When LLMs write SVG, the coordinates are never quite right. svg-aligner fixes that — deterministically."
- **License**: MIT
- **Dependencies**: Zero (stdlib only)

---

## 1. Twitter / X (English)

### Thread (4 tweets)

**Tweet 1 — Hook:**
> Ever noticed how LLM-generated SVGs have text that's slightly off? Boxes at x=120, 122, 119 when they should all be at 120?
>
> That's not a prompt problem. It's a layout problem. LLMs aren't layout engines.
>
> I built svg-aligner to fix this deterministically. Zero API calls. Zero deps.
>
> 🧵

**Tweet 2 — What it does:**
> svg-aligner works in 3 stages:
>
> 1. Resolve every element to absolute coordinates (handling nested transforms)
> 2. Detect groups within 5px of each other (threshold algorithm)
> 3. Snap them to exact alignment via inverse-CTM write-back
>
> It's deterministic. Same input = same output. Every time.

**Tweet 3 — Multi-AI pipeline:**
> Built for multi-AI collaboration:
>
> Qwen (structure) → GPT (images) → Claude Code (SVG) → svg-aligner (fix coordinates) → PPTX export
>
> Battle-tested on 300+ slides. 8 critical bugs found and fixed in hell-grade stress testing.
>
> It's the final quality gate before SVG hits PowerPoint.

**Tweet 4 — Call to action:**
> svg-aligner is MIT-licensed, zero-dependency Python:
>
> pip install git+https://github.com/synowiecsixsl5063-spec/svg-aligner.git
>
> Or just drop core.py into your project. No install needed.
>
> Star it if you generate SVG with LLMs: https://github.com/synowiecsixsl5063-spec/svg-aligner

### Single-Tweet Summary (for quick sharing)

> LLMs can't align SVG elements properly. My new project svg-aligner fixes that with a 5px threshold algorithm — no API calls, no deps. Drop it into any AI→SVG pipeline.
>
> GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner
> Built for @pptmaster_ai

---

## 2. Reddit

### r/Python — "Showcase" post

**Title**: svg-aligner — Deterministic SVG alignment post-processor for LLM-generated content (zero deps, MIT)

**Body**:
```markdown
## What My Project Does

svg-aligner is a Python post-processor that fixes pixel-level coordinate drift in LLM-generated SVG. When LLMs write SVG XML, elements that should be aligned often have 2-5px offsets — a row of boxes at `x="120"`, `x="122"`, `x="119"` instead of all at `x="120"`.

svg-aligner detects these near-misses deterministically and snaps them to exact alignment. No hallucination risk. No API costs. Same input = same output.

## Target Audience

Anyone using LLMs to generate SVG content — AI presentation tools, chart generators, diagram builders, etc. It's built for and used in pptmaster, an AI→PPTX pipeline.

## Comparison

Unlike asking the LLM to "fix the alignment" (which costs API calls and can introduce new errors), svg-aligner is:
- **Deterministic**: same input always produces same output
- **Zero-cost**: no API calls, runs locally
- **Battle-tested**: 300+ slides, 8 critical bug fixes
- **Zero dependencies**: just Python stdlib

## Links

- GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner
- Docs: README.md + INTEGRATION.md
```

### r/MachineLearning — "Research/Project" post

**Title**: [P] svg-aligner: Deterministic SVG coordinate correction for LLM-generated layouts

**Body**:
```markdown
**Problem**: LLMs generate SVG coordinates that are approximately correct but drift by 2-5 pixels. This causes visual misalignment in multi-element layouts — a fundamental limitation of having a language model act as a layout engine.

**Approach**: A 3-stage deterministic algorithm:
1. Absolute coordinate resolution via CTM composition (handling nested transforms)
2. Range-based detection with 5px hard threshold + perpendicular axis filtering
3. Inverse-CTM coordinate write-back for local attribute correction

**Key innovations**:
- Text-anchor-aware coordinate adjustment (middle/end anchors correctly mapped to visual bbox edges)
- Cross-type deduplication (each element touched by at most 1 horizontal + 1 vertical correction)
- Path element coordinate translation via regex-based `d` attribute parsing
- Zero external dependencies (stdlib only)

**Results**: 300+ pages stress-tested across multi-AI pipeline (Qwen→GPT→Claude Code). 8 critical bugs identified during testing — all fixed.

**GitHub**: https://github.com/synowiecsixsl5063-spec/svg-aligner
**License**: MIT — drop it in any project.
```

---

## 3. LinkedIn

### Post

```
[Project Launch] svg-aligner — when LLMs write SVG, the coordinates are never quite right.

Here's the problem: LLMs aren't layout engines. When they generate SVG XML, elements that should be perfectly aligned often drift by 2-5 pixels. A row of boxes at x=120, 122, 119 instead of all at x=120.

I built svg-aligner as the final quality gate in the pptmaster pipeline. It detects near-misses with a deterministic 5px threshold algorithm and snaps them to exact alignment — no API calls, no dependencies, no hallucination risk.

The numbers:
• 300+ slides stress-tested
• 8 critical bugs found and fixed
• 500 slides/second processing speed
• Zero dependencies (Python stdlib only)
• MIT licensed

It's part of a multi-AI collaboration pipeline:
Qwen (structure) → GPT (images) → Claude Code (SVG) → svg-aligner → PPTX

If you're building anything that generates SVG via LLMs, this might save you hours of debugging "why does my layout look slightly wrong?"

GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner
Integration guide included.

#OpenSource #Python #SVG #LLM #AI #pptmaster #Developer #MachineLearning
```

---

## 4. Chinese Platforms (中文社交平台)

### 🔥 主推宣传文案（广告体）

**适用场景**：微博、即刻、V2EX、知乎想法、朋友圈、微信群

```
🔥【svg-aligner：LLM生成SVG的排版革命！】🔥

⚡️还在为LLM生成的SVG文字糊成一团而抓狂？
⚡️还在为方位错误、元素重叠而熬夜调试？

✅ svg-aligner来了！
   - 5px极差阈值算法，1px级偏移？自动修正！
   - 逆向CTM回写技术，坐标精确如手术刀！
   - 跨类型去重机制，文件干净如新出厂！

🌟【效果对比】🌟
[修正前]：文字重叠、方位错误、元素乱飞
[修正后]：清晰对齐、专业排版、完美呈现

🚀【为什么选择svg-aligner？】🚀
✓ 地狱级压测验证，8个核心Bug已修复
✓ 多AI协作流程，千问→GPT→Claude Code闭环
✓ 集成pptmaster，LLM生成PPT的终极解决方案
✓ 5分钟上手，10分钟解决你的排版噩梦！

🔥【立即体验】🔥
GitHub：https://github.com/synowiecsixsl5063-spec/svg-aligner
体验页：https://synowiecsixsl5063-spec.github.io/svg-aligner
文档：https://github.com/synowiecsixsl5063-spec/svg-aligner/blob/master/README_CN.md
安装：pip install git+https://github.com/synowiecsixsl5063-spec/svg-aligner.git

📢【限时福利】📢
Star我们的项目，即送《LLM生成SVG最佳实践指南》！
```

### 知乎长文模板

**标题**: svg-aligner：解决 LLM 生成 SVG 排版灾难的确定性后处理器

**正文**:
```
在构建 pptmaster（AI 驱动的 PPT 生成系统）的过程中，我们遇到了一个棘手的问题：
LLM 手写 SVG 时，坐标总是"差一点"——

本应左对齐的三个方框，坐标却是 x="120"、x="122"、x="119"。
本应等间距排列的元素，间距却是 2px、3px、1px。

这不是 prompt 的问题，这是 LLM 的根本限制：LLM 不是排版引擎。

于是我写了一个确定性的后处理模块——svg-aligner。

核心思路很简单：5px 极差阈值算法。
- 如果一组元素的坐标极差 < 5px，就认为它们"应该对齐"
- 用逆 CTM 矩阵把修正写回元素的本地坐标
- 零依赖、确定性输出、永远不抛异常

经过了 300+ 页的地狱级压测，修了 8 个关键 bug（嵌套变换、文本锚点、path 平移等），
现在已经稳定运行在 pptmaster 的生产管线中。

GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner
MIT 协议，欢迎 Star & PR。

#人工智能 #Python #开源 #SVG #LLM
```

### 即刻 / V2EX 短帖

```
【开源项目】svg-aligner

解决 LLM 生成 SVG 的像素级坐标偏移问题。

当 LLM 手写 SVG 时，元素经常"差一点对齐"——x=120, 122, 119 而不是整齐的 x=120, 120, 120。

svg-aligner 用 5px 极差阈值算法检测并修正这些偏移：
- 零依赖，纯 Python 标准库
- 确定性输出，不调用任何 API
- 已通过 300+ 页压力测试
- MIT 协议

GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner

配合 pptmaster 使用效果更佳。
```

### 微信朋友圈/群转发

```
🚀 开源了一个小工具：svg-aligner

专门解决 LLM 生成的 SVG 坐标漂移问题——文字糊成一团？方位错误？一键搞定。

5px 极差阈值算法 + 逆向 CTM 回写 + 零依赖。
已通过 300+ 页地狱级压测，集成在 pptmaster 管线中稳定运行。

GitHub: https://github.com/synowiecsixsl5063-spec/svg-aligner
Star 即送《LLM 生成 SVG 最佳实践指南》📖
```

---

## 5. Hacker News — "Show HN"

**Title**: Show HN: svg-aligner — deterministic SVG coordinate correction for LLM output

**Body**:
```
When LLMs generate SVG XML directly (not through a rendering library), they produce coordinates that are approximately right but drift by 2-5 pixels. A row of elements that should be left-aligned might have x=120, 122, 119.

I built svg-aligner as a deterministic post-processing step for the pptmaster AI→PPTX pipeline. It uses a 5px threshold algorithm to detect "near-aligned" element groups and snaps them to exact positions.

Key properties:
- Zero external dependencies (Python stdlib only)
- Deterministic: same input → same output
- Handles nested transforms, text-anchor offsets, path elements
- Never throws: malformed input returns unchanged
- ~500 slides/second on a single core

The algorithm works in 3 stages:
1. Walk DOM tree, resolve every element to absolute root-space coordinates
2. Cluster elements within 15px window, trigger on <5px range
3. Compute correction delta, transform back through inverse CTM

It's been stress-tested on 300+ SVG pages across different document types. Eight subtle bugs were found and fixed during testing (nested transform matrix composition, text-anchor coordinate mapping, path d-attribute translation, etc.).

Happy to answer questions about the algorithm, multi-AI pipeline integration, or SVG/LLM challenges in general.
```

---

## 6. Social Media Image Captions

### For before_after_comparison.png

**Caption options**:

EN: "Before (left) vs After (right): svg-aligner detects and fixes 2-5px coordinate drift in LLM-generated SVG. Same deterministic algorithm, zero API calls."

CN: "左：LLM 生成的原始 SVG（坐标偏移 2-5px）｜ 右：svg-aligner 修正后（完美对齐）"

### For multi_ai_collaboration.png

**Caption options**:

EN: "Multi-AI collaboration pipeline: Qwen extracts → GPT generates images → Claude Code creates SVG → svg-aligner ensures pixel-perfect alignment → PPTX export."

CN: "多 AI 协作流程：千问提取结构 → GPT 生成图像 → Claude Code 创建 SVG → svg-aligner 确保像素级对齐 → PPTX 导出"

---

## 7. GitHub Profile README Badge

Add to your GitHub profile README:

```markdown
[![svg-aligner](https://img.shields.io/badge/svg--aligner-LLM_SVG_Alignment-blue?style=flat-square&logo=github)](https://github.com/synowiecsixsl5063-spec/svg-aligner)
```

Rendered:

[![svg-aligner](https://img.shields.io/badge/svg--aligner-LLM_SVG_Alignment-blue?style=flat-square&logo=github)](https://github.com/synowiecsixsl5063-spec/svg-aligner)
