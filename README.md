# textbook-to-notion-review

一个 Claude Code / Claude.ai 技能（skill）。它把教材 PDF 整理成按章节分册的考试复习资料，再导入 Notion，在 Notion 里自测、问答和追踪进度。扫描件也能处理。

每章固定四节：知识点清单 → 核心内容 → 易错点 → 典型题。典型题的答案放在 Notion 的折叠块里，先做题再展开。

## 能做什么

- **盘点教材 PDF**：页数、有没有文字层、书签情况，以及书上印的页码和 PDF 页码之间的偏移。扫描件可以渲染目录页，看图转写目录。
- **规划和撰写分册**：指定教材优先，资料里写书上印的页码，标出各书写法不同的地方，计算题的答案用 Python 复算。
- **自检**：检查格式（缺小节、缺答案、缺页码），汇总知识点总清单。
- **转换成 Notion 内容**：
  - 答案放进折叠块，自动转义 `<`，表格前后补空行，提示单元格里的竖线。
  - 过长的章自动拆成几段上传。
  - 生成知识点数据库的结构和数据行。
- **上传 Notion 和上传后核对**：给出上传顺序、并行策略和上传后的核对清单。

## 安装

- **Claude Code**：把本目录放到 `~/.claude/skills/textbook-to-notion-review/`。
- **Claude.ai**：在技能设置里上传打包好的 `.skill` 文件。

导入 Notion 需要先连接 Notion 连接器。

## 依赖

- Python 3
- PyMuPDF：`pip install pymupdf`

## 目录结构

```
SKILL.md                    工作流程（第 0–6 步）
references/
  volume_format.md          分册格式与写作规则（脚本按这个格式解析）
  notion_build.md           Notion 页面结构、上传步骤、Markdown 坑、核对清单、复习用法
scripts/
  pdf_probe.py              盘点 PDF / 渲染页面 / 推算页码偏移
  lint_volumes.py           分册格式检查
  build_checklist.py        汇总知识点总清单
  md_to_notion.py           转换为 Notion 页面内容、上传计划和数据库行
```

## 脚本用法

```bash
python scripts/pdf_probe.py <教材目录>                          # 盘点（加 --recursive 扫子目录）
python scripts/pdf_probe.py 某书.pdf --render 5-14 --out toc     # 渲染目录页
python scripts/lint_volumes.py <资料目录>
python scripts/build_checklist.py <资料目录> 清单.md
python scripts/md_to_notion.py <资料目录> <输出目录> --single 09 --vol-label "01=01 短名"
```
