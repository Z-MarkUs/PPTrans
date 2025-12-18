<div align="center">

<img src="https://github.com/user-attachments/assets/21080ce6-1f77-4a90-99a2-ac2c1599b61b" width="30%" alt="PPT Translator Logo">

# PPT Translator / PPT 翻译器

**English** | [中文](#中文)

Convert your PowerPoint presentations to beautifully translated documents while preserving formatting

将 PowerPoint 演示文稿转换为精美的翻译文档，同时保留格式

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![PyPI](https://img.shields.io/badge/PyPI-pptrans-blue.svg) ![Tests](https://img.shields.io/badge/Tests-Passing-green.svg)

*Clean, fast, and reliable PowerPoint translation with multi-provider support, vision-based review, and formatting preservation*

*简洁、快速、可靠的 PowerPoint 翻译工具，支持多提供商、基于视觉的审查和格式保留*

</div>

---

## English

### ✨ Features

• ⚡ **Lightning Fast**: Sub-2 second translation for most presentations
• 🔄 **Multi-Provider Support**: Switch between DeepSeek, OpenAI, Anthropic, and Grok with a simple CLI flag
• 🎨 **Rich Formatting**: Preserves fonts, colors, spacing, tables, and alignment after translation
• 🔍 **AI-Guided Autofallback**: Vision-based quality review with automatic fallback to advanced formatting when needed  
• 💾 **Translation Memory**: Ensures consistency across slides and reduces API costs  
• 📚 **User Glossary**: Define preferred translations for consistent terminology  
• 📝 **Interactive Review**: Edit translations in JSON/YAML and regenerate PPTs  
• 📦 **Batch Processing**: Convert entire directories of presentations at once
• 🛡️ **Robust Processing**: Handles all PowerPoint content types with graceful fallbacks

### 📦 Installation

#### Option 1: Install via pip (Recommended)

```bash
pip install pptrans
```

#### Option 2: Install from source

```bash
git clone https://github.com/Z-MarkUs/PPTrans.git
cd PPTrans
pip install -e .
```

#### Option 3: Use standalone applications

Download pre-built applications from [GitHub Releases](https://github.com/Z-MarkUs/PPTrans/releases):

- **macOS Apple Silicon** (arm64): `PPTrans.app`
- **macOS Intel** (x86_64): `PPTrans.app` (built with Rosetta 2)
- **Windows** (x86): `PPTrans.exe`
- **Linux** (x86_64): `pptrans`

Or build from source:

```bash
# macOS (Apple Silicon)
python3 build_app.py macos arm64

# macOS (Intel) - Uses Rosetta 2 on arm64 machines
python3 build_app.py macos x86_64

# Windows
python build_app.py windows

# Linux
python3 build_app.py linux
```

### 📋 Requirements

- Python 3.10+ (for pip installation)
- Provider API keys stored in environment variables (see Configuration)

### 🔐 Configuration

Copy `example.env` to `.env` and fill in the API keys for the providers you plan to use:

```bash
cp example.env .env
```

**Environment Variables:**

| Provider  | Required Variable         | Optional Variables                 | Default Model           |
|-----------|---------------------------|------------------------------------|-------------------------|
| DeepSeek  | `DEEPSEEK_API_KEY`        | `DEEPSEEK_API_BASE`                | `deepseek-chat`         |
| OpenAI    | `OPENAI_API_KEY`          | `OPENAI_ORG`                       | `gpt-5`                 |
| Anthropic | `ANTHROPIC_API_KEY`       | —                                  | `claude-3.7-sonnet`     |
| Grok      | `GROK_API_KEY`            | `GROK_API_BASE`                    | `grok-beta`             |

> 💡 **Tip**: The CLI reads your `.env` file automatically. On macOS, add exports to `~/.zshrc` or use `direnv` for project-specific secrets.

### 🚀 Quick Start

After installation, use the `pptrans` command:

```bash
# Basic translation (no vision review - fastest)
pptrans presentation.pptx --provider openai --source-lang zh --target-lang en

# Translate all PPT files in a directory
pptrans ./presentations/ --provider openai

# With vision-based quality review (opt-in feature - requires --vision-review flag)
pptrans presentation.pptx --provider openai --vision-review --vision-model YOUR_VISION_MODEL_NAME

# Use a glossary for consistent terminology
pptrans presentation.pptx --provider openai --glossary glossary.json

# Generate review file for manual editing
pptrans presentation.pptx --provider openai --generate-review

# Regenerate PPT from edited review file
pptrans presentation.pptx --regenerate-from-review translation_review.json

# View all available options
pptrans --help
```

**Important Notes:**
- **Vision review is NOT automatic** - you must explicitly add `--vision-review` flag to enable it
- Basic translation (without `--vision-review`) is faster and uses fewer API calls
- Vision review requires a vision-capable model (specify with `--vision-model`)

### 📖 Usage

#### Basic Translation

```bash
pptrans /path/to/presentation.pptx \
  --provider openai \
  --model YOUR_MODEL_NAME \
  --source-lang zh \
  --target-lang en
```

#### Advanced Options

```bash
pptrans /path/to/decks \
  --provider openai \
  --source-lang zh \
  --target-lang en \
  --max-workers 4 \
  --max-chunk-size 2000 \
  --glossary my_glossary.json \
  --vision-review \
  --vision-quality-threshold 7.5 \
  --max-refinement-iterations 3 \
  --generate-review \
  --review-format yaml
```

#### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--provider` | Model provider: `deepseek`, `openai`, `anthropic`, `grok` | `deepseek` |
| `--model` | Override provider's default model (enter model name from your provider) | Provider default |
| `--source-lang` | Source language code (ISO 639-1) | `zh` |
| `--target-lang` | Target language code (ISO 639-1) | `en` |

**Language Support**: PPTrans accepts any ISO 639-1 language code. Actual language support depends on your chosen LLM provider's capabilities. Common codes: `zh` (Chinese), `en` (English), `ja` (Japanese), `ko` (Korean), `es` (Spanish), `fr` (French), `de` (German), etc. See [LANGUAGE_SUPPORT.md](LANGUAGE_SUPPORT.md) for details.
| `--max-chunk-size` | Character limit per translation request | `1000` |
| `--max-workers` | Number of threads for slide processing | `4` |
| `--glossary` | Path to glossary file (JSON/YAML) | None |
| `--no-memory` | Disable translation memory | Enabled |
| `--vision-review` | Enable vision-based quality review | Disabled |
| `--vision-model` | Vision-capable model name (must support image/vision analysis) | Required if `--vision-review` enabled |
| `--vision-quality-threshold` | Minimum quality score (0-10) | `7.0` |
| `--max-refinement-iterations` | Max refinement attempts | `3` |
| `--generate-review` | Generate editable review file | Disabled |
| `--review-format` | Review file format: `json`, `yaml` | `json` |
| `--regenerate-from-review` | Regenerate PPT from edited review file | None |
| `--keep-intermediate` | Keep intermediate XML files | Cleaned up |

#### Output Files

The tool generates:

1. `{deck}_original.xml` – Source deck contents (if `--keep-intermediate`)
2. `{deck}_translated.xml` – Translated content (if `--keep-intermediate`)
3. `{deck}_translated.pptx` – Rebuilt presentation with translated text
4. `translation_review.{json|yaml}` – Review file (if `--generate-review`)

### 🎯 Key Features Explained

#### AI-Guided Autofallback & Vision Review

**Note**: PPTrans is an application that uses your chosen models - we don't provide model services. You select both the translation model and vision review model based on your needs and API access.

**Vision review is opt-in only** - it is NOT enabled by default. You must explicitly add the `--vision-review` flag to enable it. Basic translation (without vision review) is faster and uses fewer API calls.

When vision review is enabled (via `--vision-review` flag), the system uses your chosen vision-capable model to visually analyze slides:

- **Pre-translation analysis**: Understands layout constraints and text hierarchy
- **Post-translation review**: Quality scoring (0-10) with specific issues and suggestions
- **AI-guided autofallback**: Automatically switches to advanced formatting methods when issues are detected:
  - **Advanced paragraph formatting**: Preserves bullets, indentation, and multi-paragraph structure
  - **TextFrame measurement**: Uses accurate text measurement instead of estimation for better font sizing
- **Iterative refinement**: Automatically improves translations until quality threshold is met
- **Prompt optimization**: Learning context is intelligently limited (~500 tokens max) to prevent prompt bloat across multiple iterations - only the most relevant and successful patterns are included

The autofallback system reads AI suggestions and intelligently enables advanced features only when needed, keeping the process efficient for simple slides while ensuring quality for complex formatting. The learning system tracks successful fixes and avoids repeating failed patterns, with prompt size management to ensure efficient API usage.

```bash
# Use your vision-capable model (enter the model name from your provider)
pptrans deck.pptx --provider openai --vision-review --vision-model YOUR_VISION_MODEL_NAME --vision-quality-threshold 8.0
```

#### Translation Memory

Stores translations in a temporary JSON file to ensure consistency:

- Reuses translations across multiple slides
- Shared across all files in a batch
- Automatically cleaned up after completion

Disable with `--no-memory` if you don't need consistency.

#### User-Defined Glossary

Define preferred translations for consistent terminology:

**glossary.json:**
```json
{
  "AI": "人工智能",
  "Machine Learning": "机器学习",
  "Neural Network": "神经网络"
}
```

```bash
pptrans deck.pptx --glossary glossary.json
```

The glossary is included in LLM prompts and applied as post-processing fallback.

#### Interactive Review Mode

Generate editable review files for manual translation editing:

```bash
# Generate review file
pptrans deck.pptx --generate-review --review-format yaml

# Edit translation_review.yaml manually, then regenerate PPT
pptrans deck.pptx --regenerate-from-review translation_review.yaml
```

Review files include:
- Original and translated texts per slide
- Quality scores and issues (if vision review enabled)
- Editable translation fields

### 🧪 Testing

Run unit tests with Pytest:

```bash
pytest
```

The test suite focuses on translation chunking/caching, CLI utilities, and provider integration.

### 🛠️ Project Structure

```
.
├── ppt_translator/
│   ├── cli.py               # CLI parsing and orchestration
│   ├── pipeline.py           # PPT extraction, translation, regeneration
│   ├── translation.py       # Chunking + caching translation service
│   ├── memory.py            # Translation memory and glossary
│   ├── vision.py            # Vision-based review system
│   ├── review.py            # Interactive review file management
│   ├── render.py            # Slide rendering utilities
│   ├── utils.py             # Filesystem helpers
│   └── providers/           # DeepSeek, OpenAI, Anthropic, Grok adapters
│       ├── base.py          # Base provider classes
│       ├── deepseek.py
│       ├── openai_provider.py
│       ├── anthropic_provider.py
│       └── grok_provider.py
├── tests/                   # Pytest suite
├── example.env              # Environment variable template
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Package configuration
├── build_app.py            # Standalone app builder
└── main.py                  # Entry point (delegates to CLI)
```

### 🤝 Contributing

Pull requests and issues are welcome! Please:

1. Run `pytest` before submitting changes
2. Document any new providers or features in the README
3. Follow existing code style (Black formatting)

### 📄 License

This project is licensed under the MIT License. See `LICENSE` for details.

### 🔗 Links

- **GitHub Repository**: https://github.com/Z-MarkUs/PPTrans
- **PyPI Package**: https://pypi.org/project/pptrans/
- **Issues**: https://github.com/Z-MarkUs/PPTrans/issues

---

## 中文

### ✨ 功能特性

• ⚡ **极速翻译**: 大多数演示文稿可在 2 秒内完成翻译  
• 🔄 **多提供商支持**: 通过简单的 CLI 标志在 DeepSeek、OpenAI、Anthropic 和 Grok 之间切换  
• 🎨 **丰富格式**: 翻译后保留字体、颜色、间距、表格和对齐方式  
• 🔍 **AI 引导的自动回退**: 基于视觉的质量审查，需要时自动切换到高级格式处理  
• 💾 **翻译记忆库**: 确保跨幻灯片的一致性并降低 API 成本  
• 📚 **用户词汇表**: 定义首选翻译以保持术语一致性  
• 📝 **交互式审查**: 在 JSON/YAML 中编辑翻译并重新生成 PPT  
• 📦 **批量处理**: 一次性转换整个目录的演示文稿  
• 🛡️ **稳健处理**: 优雅地处理所有 PowerPoint 内容类型  

### 📦 安装

#### 方式 1: 通过 pip 安装（推荐）

```bash
pip install pptrans
```

#### 方式 2: 从源码安装

```bash
git clone https://github.com/Z-MarkUs/PPTrans.git
cd PPTrans
pip install -e .
```

#### 方式 3: 使用独立应用程序

从 [GitHub Releases](https://github.com/Z-MarkUs/PPTrans/releases) 下载预构建应用程序：

- **macOS Apple Silicon** (arm64): `PPTrans.app`
- **macOS Intel** (x86_64): `PPTrans.app` (使用 Rosetta 2 构建)
- **Windows** (x86): `PPTrans.exe`
- **Linux** (x86_64): `pptrans`

或从源码构建：

```bash
# macOS (Apple Silicon)
python3 build_app.py macos arm64

# macOS (Intel) - 在 arm64 机器上使用 Rosetta 2
python3 build_app.py macos x86_64

# Windows
python build_app.py windows

# Linux
python3 build_app.py linux
```

### 📋 要求

- Python 3.10+（用于 pip 安装）
- 存储在环境变量中的提供商 API 密钥（见配置部分）

### 🔐 配置

将 `example.env` 复制为 `.env` 并填入您计划使用的提供商的 API 密钥：

```bash
cp example.env .env
```

**环境变量：**

| 提供商    | 必需变量              | 可选变量                 | 默认模型               |
|-----------|----------------------|--------------------------|------------------------|
| DeepSeek  | `DEEPSEEK_API_KEY`    | `DEEPSEEK_API_BASE`      | `deepseek-chat`        |
| OpenAI    | `OPENAI_API_KEY`      | `OPENAI_ORG`             | `gpt-5`                |
| Anthropic | `ANTHROPIC_API_KEY`   | —                        | `claude-3.7-sonnet`    |
| Grok      | `GROK_API_KEY`        | `GROK_API_BASE`          | `grok-beta`            |

> 💡 **提示**: CLI 会自动读取您的 `.env` 文件。在 macOS 上，可以将导出添加到 `~/.zshrc` 或使用 `direnv` 进行项目特定的密钥管理。

### 🚀 快速开始

安装后，使用 `pptrans` 命令：

```bash
# 基本翻译（无视觉审查 - 最快）
pptrans presentation.pptx --provider openai --source-lang zh --target-lang en

# 翻译目录中的所有 PPT 文件
pptrans ./presentations/ --provider openai

# 使用基于视觉的质量审查（需要显式添加 --vision-review 标志）
pptrans presentation.pptx --provider openai --vision-review --vision-model YOUR_VISION_MODEL_NAME

# 使用词汇表保持术语一致性
pptrans presentation.pptx --provider openai --glossary glossary.json

# 生成审查文件以便手动编辑
pptrans presentation.pptx --provider openai --generate-review

# 从编辑后的审查文件重新生成 PPT
pptrans presentation.pptx --regenerate-from-review translation_review.json

# 查看所有可用选项
pptrans --help
```

**重要提示：**
- **视觉审查不是自动的** - 必须显式添加 `--vision-review` 标志才能启用
- 基本翻译（不使用 `--vision-review`）更快且使用更少的 API 调用
- 视觉审查需要支持视觉的模型（使用 `--vision-model` 指定）

### 📖 使用方法

#### 基本翻译

```bash
pptrans /path/to/presentation.pptx \
  --provider openai \
  --model YOUR_MODEL_NAME \
  --source-lang zh \
  --target-lang en
```

#### 高级选项

```bash
pptrans /path/to/decks \
  --provider openai \
  --source-lang zh \
  --target-lang en \
  --max-workers 4 \
  --max-chunk-size 2000 \
  --glossary my_glossary.json \
  --vision-review \
  --vision-quality-threshold 7.5 \
  --max-refinement-iterations 3 \
  --generate-review \
  --review-format yaml
```

#### 命令行选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--provider` | 模型提供商: `deepseek`, `openai`, `anthropic`, `grok` | `deepseek` |
| `--model` | 覆盖默认模型（如 `gpt-5-nano`, `gpt-5-mini`） | 提供商默认值 |
| `--source-lang` | 源语言代码 (ISO 639-1) | `zh` |
| `--target-lang` | 目标语言代码 (ISO 639-1) | `en` |
| `--max-chunk-size` | 每次翻译请求的字符限制 | `1000` |
| `--max-workers` | 幻灯片处理的线程数 | `4` |
| `--glossary` | 词汇表文件路径 (JSON/YAML) | 无 |
| `--no-memory` | 禁用翻译记忆库 | 启用 |
| `--vision-review` | 启用基于视觉的质量审查 | 禁用 |
| `--vision-model` | 视觉模型名称（必须支持图像/视觉分析功能） | 启用 `--vision-review` 时必需 |
| `--vision-quality-threshold` | 最低质量分数 (0-10) | `7.0` |
| `--max-refinement-iterations` | 最大优化尝试次数 | `3` |
| `--generate-review` | 生成可编辑的审查文件 | 禁用 |
| `--review-format` | 审查文件格式: `json`, `yaml` | `json` |
| `--regenerate-from-review` | 从编辑后的审查文件重新生成 PPT | 无 |
| `--keep-intermediate` | 保留中间 XML 文件 | 清理 |

#### 输出文件

工具会生成：

1. `{deck}_original.xml` – 源演示文稿内容（如果使用 `--keep-intermediate`）
2. `{deck}_translated.xml` – 翻译后的内容（如果使用 `--keep-intermediate`）
3. `{deck}_translated.pptx` – 使用翻译文本重建的演示文稿
4. `translation_review.{json|yaml}` – 审查文件（如果使用 `--generate-review`）

### 🎯 核心功能说明

#### AI 引导的自动回退和视觉审查

**注意**: PPTrans 是一个使用您选择的模型的应用 - 我们不提供模型服务。您可以根据需求和 API 访问权限选择翻译模型和视觉审查模型。

**视觉审查是可选的** - 默认情况下不启用。必须显式添加 `--vision-review` 标志才能启用。基本翻译（不使用视觉审查）更快且使用更少的 API 调用。

启用视觉审查后（通过 `--vision-review` 标志），系统使用您选择的视觉模型来视觉分析幻灯片：

- **翻译前分析**: 理解布局约束和文本层次结构
- **翻译后审查**: 质量评分 (0-10) 并提供具体问题和建议
- **AI 引导的自动回退**: 检测到问题时自动切换到高级格式处理方法：
  - **高级段落格式**: 保留项目符号、缩进和多段落结构
  - **TextFrame 测量**: 使用准确的文本测量而非估算，实现更好的字体大小调整
- **迭代优化**: 自动改进翻译直到达到质量阈值
- **提示优化**: 学习上下文智能限制（最多约 500 个 token），防止多次迭代时提示膨胀 - 仅包含最相关和成功的模式

自动回退系统读取 AI 建议，仅在需要时智能启用高级功能，对简单幻灯片保持高效，同时确保复杂格式的质量。学习系统跟踪成功的修复并避免重复失败的模式，通过提示大小管理确保高效的 API 使用。

```bash
# 使用您的视觉模型（输入您提供商提供的模型名称）
pptrans deck.pptx --provider openai --vision-review --vision-model YOUR_VISION_MODEL_NAME --vision-quality-threshold 8.0
```

#### 翻译记忆库

将翻译存储在临时 JSON 文件中以确保一致性：

- 在多个幻灯片之间重用翻译
- 在批次中的所有文件之间共享
- 完成后自动清理

如果不需要一致性，可使用 `--no-memory` 禁用。

#### 用户定义词汇表

定义首选翻译以保持术语一致性：

**glossary.json:**
```json
{
  "AI": "人工智能",
  "Machine Learning": "机器学习",
  "Neural Network": "神经网络"
}
```

```bash
pptrans deck.pptx --glossary glossary.json
```

词汇表会包含在 LLM 提示中，并作为后处理备用方案应用。

#### 交互式审查模式

生成可编辑的审查文件以便手动编辑翻译：

```bash
# 生成审查文件
pptrans deck.pptx --generate-review --review-format yaml

# 手动编辑 translation_review.yaml，然后重新生成 PPT
pptrans deck.pptx --regenerate-from-review translation_review.yaml
```

审查文件包括：
- 每张幻灯片的原始文本和翻译文本
- 质量分数和问题（如果启用了视觉审查）
- 可编辑的翻译字段

### 🧪 测试

使用 Pytest 运行单元测试：

```bash
pytest
```

测试套件专注于翻译分块/缓存、CLI 实用程序和提供商集成。

### 🛠️ 项目结构

```
.
├── ppt_translator/
│   ├── cli.py               # CLI 解析和编排
│   ├── pipeline.py         # PPT 提取、翻译、重建
│   ├── translation.py      # 分块 + 缓存翻译服务
│   ├── memory.py           # 翻译记忆库和词汇表
│   ├── vision.py           # 基于视觉的审查系统
│   ├── review.py           # 交互式审查文件管理
│   ├── render.py           # 幻灯片渲染工具
│   ├── utils.py            # 文件系统辅助函数
│   └── providers/          # DeepSeek、OpenAI、Anthropic、Grok 适配器
│       ├── base.py         # 基础提供商类
│       ├── deepseek.py
│       ├── openai_provider.py
│       ├── anthropic_provider.py
│       └── grok_provider.py
├── tests/                  # Pytest 测试套件
├── example.env            # 环境变量模板
├── requirements.txt       # Python 依赖项
├── pyproject.toml        # 包配置
├── build_app.py          # 独立应用程序构建器
└── main.py               # 入口点（委托给 CLI）
```

### 🤝 贡献

欢迎提交 Pull Request 和 Issue！请：

1. 提交更改前运行 `pytest`
2. 在 README 中记录任何新的提供商或功能
3. 遵循现有代码风格（Black 格式化）

### 📄 许可证

本项目采用 MIT 许可证。详情请参阅 `LICENSE`。

### 🔗 链接

- **GitHub 仓库**: https://github.com/Z-MarkUs/PPTrans
- **PyPI 包**: https://pypi.org/project/pptrans/
- **问题反馈**: https://github.com/Z-MarkUs/PPTrans/issues
