# DeepPaperNote Onboarding Prompt

Use this prompt after installing `DeepPaperNote` into Codex.

Its purpose is simple:
- help a new user discover which configuration items matter
- auto-detect what can already be inferred from the local machine
- explain optional integrations clearly
- offer to configure the missing pieces

If the short commands already work well for you, prefer those first:
- `/deeppapernote doctor`
- `/deeppapernote start`

## Chinese Prompt

```text
我刚安装了 DeepPaperNote。请你帮我做一次 DeepPaperNote 的初始化检查和配置引导。

请按下面的顺序进行：

1. 先检查当前环境里 DeepPaperNote 运行最关键的配置项是否已经具备：
   - Obsidian vault 路径
   - DeepPaperNote 默认输出目录配置
   - Zotero MCP 是否可用
   - OCR 相关环境是否可用
   - Semantic Scholar API key 是否已配置

2. 对每一项都明确告诉我：
   - 这项配置是不是必需的
   - 如果不配置，会影响什么
   - 如果已经配置好了，请告诉我当前检测到的值
   - 如果还没配置，请告诉我推荐配置方式

3. 尽量自动发现本机上的信息，不要一开始就把问题都抛给我。
   例如：
   - 如果能找到可能的 Obsidian vault 路径，就先告诉我你找到了什么
   - 如果能判断 Zotero MCP 已经可用，就直接告诉我
   - 如果能判断 OCR 工具已经安装，就直接告诉我

4. 如果某项可以由你直接帮我完成配置，请先告诉我会修改什么，再征求我的确认。

5. 最后给我一个清晰的总结，分成三类：
   - 已完成配置
   - 推荐补充配置
   - 可选但有帮助的增强配置

如果你认为合适，也可以在最后问我是否要你继续直接帮我把缺失的配置补好。
```

## English Prompt

```text
I just installed DeepPaperNote. Please help me run an initial DeepPaperNote setup check and configuration walkthrough.

Please do this in order:

1. Check whether the key environment pieces for DeepPaperNote are already available:
   - Obsidian vault path
   - DeepPaperNote output directory configuration
   - Zotero MCP availability
   - OCR environment availability
   - Semantic Scholar API key

2. For each item, clearly tell me:
   - whether it is required
   - what happens if it is not configured
   - if it is already configured, what value you detected
   - if it is missing, what you recommend

3. Try to auto-detect local information first rather than asking me everything up front.
   For example:
   - if you can find likely Obsidian vault paths, show me what you found
   - if Zotero MCP is already available, say so directly
   - if OCR tools are already installed, say so directly

4. If there is anything you can configure directly for me, first explain what you would change and then ask for confirmation.

5. End with a clear summary grouped into:
   - already configured
   - recommended next configuration
   - optional but helpful enhancements

If it makes sense, you can also ask whether I want you to directly finish the missing setup steps.
```
