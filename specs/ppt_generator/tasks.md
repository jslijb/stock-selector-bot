# PPT 生成 - 任务清单

## 任务拆分

### Task 1: src/ppt/__init__.py
- 模块入口，导出公开 API
- 预估复杂度: 低

### Task 2: src/ppt/templates.py
- 定义幻灯片模板常量：
  - 配色方案（TITLE_COLOR, BODY_COLOR, ACCENT_COLOR）
  - 字体（CN_FONT, EN_FONT）
  - 幻灯片尺寸（16:9）
  - 字号（TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE）
- 封装 `apply_theme(prs)` 统一基调
- 预估复杂度: 低

### Task 3: src/ppt/content_parser.py
- `parse_markdown(text)` → 按 `#`/`##`/`###` 拆分段落
- `parse_plain_text(text)` → 按双换行拆分段落
- `extract_numbers(text)` → 识别数值
- 数据类 `SlideContent`
- 预估复杂度: 中

### Task 4: src/ppt/image_decider.py
- `should_include_image(slide)` → 布尔判断
- `decide_image_type(slide)` → "chart"/"user_image"/"none"
- 规则：≥3 个数值 → 图表；有 image_paths → 用户图片；其他 → 无
- 预估复杂度: 低

### Task 5: src/ppt/chart_renderer.py
- `render_bar_chart(data, title)` → 返回 BytesIO
- `render_pie_chart(data, title)` → 返回 BytesIO
- `render_line_chart(data, title)` → 返回 BytesIO
- 中文字体兼容（Windows: 微软雅黑, Linux: fallback）
- 预估复杂度: 中

### Task 6: src/ppt/generator.py
- `PptGenerator` 类:
  - `add_cover_slide(title, subtitle, date)`
  - `add_text_slide(title, bullets)`
  - `add_image_slide(title, bullets, image_path/chart)`
  - `add_end_slide()`
- `generate_ppt(content, output_path, title, image_dir, use_llm)` 主函数
- 调用 ContentParser → ImageDecider → ChartRenderer → python-pptx
- 预估复杂度: 高

### Task 7: CLI 集成 → src/interface/cli.py
- 新增 `@click.option("--ppt", "-ppt", ...)` 
- 参数: `file_path` (必需), `--img-dir`, `--title`, `--no-llm`
- 调用 `generate_ppt()`
- 预估复杂度: 中

### Task 8: 选股联动 → src/scheduler.py
- `-p2 --ppt` 完成补跑后自动生成选股报告 PPT
- 复用 `generate_ppt()` API
- 预估复杂度: 低

### Task 9: 测试验证
- 创建测试 .md 文件
- 运行 `python main.py -ppt test.md`
- 验证 .pptx 生成正确
- 清理测试文件
- 预估复杂度: 中

---

## 依赖关系

```
Task 2 (templates)
    ↓
Task 3 (content_parser) ──┐
Task 4 (image_decider)  ──┼──→ Task 6 (generator) ──→ Task 7 (CLI) ──→ Task 8 (联动)
Task 5 (chart_renderer) ──┘                              │
                                                         ↓
                                                    Task 9 (测试)
```

## 执行顺序

1. Task 1 + Task 2 并行
2. Task 3 + Task 4 + Task 5 并行（依赖 Task 2）
3. Task 6（依赖 Task 3/4/5）
4. Task 7 + Task 8（依赖 Task 6）
5. Task 9（依赖 Task 7/8）