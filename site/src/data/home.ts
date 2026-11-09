export type Locale = "en" | "zh";

/** Note excerpt blocks. Inline `**bold**` and `==highlight==` are rendered; the first highlight anchors the connector line. */
export type NoteBlock =
  | { kind: "caption"; text: string }
  | { kind: "p"; text: string }
  | { kind: "table"; headers: string[]; rows: string[][]; numeric: number[]; highlight?: number };

export type HomePageContent = {
  lang: string;
  title: string;
  description: string;
  brandHomeLabel: string;
  navLabel: string;
  headerActionsLabel: string;
  languageSwitchLabel: string;
  themeSwitchLabel: string;
  githubStarsLabel: string;
  starsFallback: string;
  starsAriaTemplate: string;
  installLabel: string;
  nav: {
    features: string;
    showcase: string;
    wiki: string;
    install: string;
  };
  languageNames: {
    en: string;
    zh: string;
  };
  theme: {
    system: string;
    light: string;
    dark: string;
    systemLabel: string;
    lightLabel: string;
    darkLabel: string;
  };
  hero: {
    badge: string;
    title: string;
    body: string;
    bodyStrong: string;
    actionsLabel: string;
    install: string;
    github: string;
    demoLabel: string;
    demoTitle: string;
  };
  features: {
    title: string;
    body: string;
    cards: Array<{
      tag: string;
      title: string;
      body: string;
      className: string;
    }>;
  };
  showcase: {
    title: string;
    body: string;
    paperLabel: string;
    noteLabel: string;
    pairs: Array<{
      title: string;
      paper: { src: string; alt: string; caption: string; box: [number, number, number, number] };
      note: { path: string; blocks: NoteBlock[] };
    }>;
  };
  wiki: {
    title: string;
    body: string;
    coreLabel: string;
    coreTree: string;
    skills: Array<{
      name: string;
      body: string;
      phrase: string;
    }>;
    rhythmLabel: string;
    rhythm: string[];
  };
  install: {
    title: string;
    body: string;
    updateLabel: string;
    updateHref: string;
    commandsLabel: string;
    tabs: Array<{ id: string; label: string; comment: string; command: string }>;
    steps: Array<{ comment: string; command: string }>;
  };
  closingNote: string;
  footer: {
    by: string;
    github: string;
    releases: string;
    issues: string;
  };
};

export const homePages: Record<Locale, HomePageContent> = {
  en: {
    lang: "en",
    title: "DeepPaperNote | Turn one dense paper into an Obsidian note worth keeping",
    description:
      "Hand DeepPaperNote a paper, and it reads the full text, writes an illustrated deep-reading note, saves it into your Obsidian vault, and links it to the papers you have read.",
    brandHomeLabel: "DeepPaperNote home",
    navLabel: "Page sections",
    headerActionsLabel: "Header actions",
    languageSwitchLabel: "Language",
    themeSwitchLabel: "Color theme",
    githubStarsLabel: "DeepPaperNote GitHub stars",
    starsFallback: "Stars",
    starsAriaTemplate: "{count} stars on GitHub",
    installLabel: "Install",
    nav: {
      features: "Why",
      showcase: "The note",
      wiki: "Wiki",
      install: "Install",
    },
    languageNames: {
      en: "English",
      zh: "Chinese",
    },
    theme: {
      system: "System",
      light: "Light",
      dark: "Dark",
      systemLabel: "Use system color theme",
      lightLabel: "Use light color theme",
      darkLabel: "Use dark color theme",
    },
    hero: {
      badge: "v3.0.0 is out",
      title: "Turn one dense paper into an Obsidian note worth keeping.",
      body:
        "DeepPaperNote is an agent skill that runs in Claude Code, Codex, and any other agent that supports skills. Hand it a paper, and it reads the full text, writes an illustrated deep-reading note, saves it into your Obsidian vault, and links it to the other papers you have read.",
      bodyStrong: "Every paper you read grows your academic wiki.",
      actionsLabel: "Primary actions",
      install: "Install",
      github: "View GitHub",
      demoLabel: "DeepPaperNote animated product demo",
      demoTitle: "DeepPaperNote animated product demo",
    },
    features: {
      title: "Why DeepPaperNote",
      body: "From one sentence to a note you can trust and actually use.",
      cards: [
        {
          tag: "Effortless",
          title: "One sentence, one note",
          body:
            "No prompts to learn, no templates to set up. Give it a title, DOI, arXiv ID, or PDF, and it finds the paper, reads it in full, extracts the figures, and saves the note into your vault.",
          className: "card-yellow",
        },
        {
          tag: "Expert",
          title: "Reads like a domain expert",
          body:
            "From CS and AI to medicine, psychology, and the humanities, each of 10 paper types gets its own way of reading, drawn from more than 50 reviewer guidelines and reporting standards and tested on 34 real papers.",
          className: "card-mint",
        },
        {
          tag: "Trustworthy",
          title: "Accurate and complete",
          body:
            "Every conclusion traces back to the paper, numbers come straight from its text and tables, and every main experiment is covered. Each note passes an independent review and a strict quality check before saving, and when the full text cannot be read, it never makes one up.",
          className: "card-rose",
        },
        {
          tag: "Visual",
          title: "Figures, tables, and formulas in the text",
          body:
            "Figures and tables are cropped from the PDF and placed where the note discusses them, and formulas render in Obsidian. No more flipping back to the PDF.",
          className: "card-yellow",
        },
        {
          tag: "Your vault",
          title: "A vault that knows you better the more you use it",
          body:
            "Each note links to related papers in your vault and goes into the domain folders you already use. Record your research directions, and each note's Takeaways tell you what the paper means for your own work.",
          className: "card-mint",
        },
      ],
    },
    showcase: {
      title: "The output is the product.",
      body:
        "Every claim in the note traces back to a page, a figure, or a table in the paper.",
      paperLabel: "Paper",
      noteLabel: "Note",
      pairs: [
      {
        title: "Figures sit right next to the explanation",
        paper: {
          src: "showcase/paper-figure-1.png",
          alt: "Paper Figure 1: the Transformer model architecture",
          caption: "Paper · p. 3 · Figure 1",
          box: [63, 84.5, 95, 93],
        },
        note: {
          path: "Method › Method Workflow",
          blocks: [
            { kind: "caption", text: "Original paper item: Figure 1. The complete encoder-decoder architecture, including shifted target inputs, positional additions, residual paths, and the output probability head. Source p. 3." },
            { kind: "p", text: "Training and generation use the same conditional prediction structure with different target inputs. During training, ==shifted reference tokens provide the preceding targets==, a practice commonly called teacher forcing. All known target positions can then be processed together under the causal mask. During generation, the next target is unknown until the decoder predicts it, so generation still proceeds one token at a time. [Sections 3 and 6.1]" },
          ],
        },
      },
      {
        title: "Numbers from the paper, contradictions included",
        paper: {
          src: "showcase/paper-table-2.png",
          alt: "Paper Table 2: BLEU scores and training cost",
          caption: "Paper · p. 8 · Table 2",
          box: [55.5, 89.5, 63.5, 99],
        },
        note: {
          path: "Experimental Evidence › Translation quality",
          blocks: [
            {
              kind: "table",
              headers: ["Model from Table 2", "English-German BLEU", "English-French BLEU"],
              rows: [
                ["MoE", "26.03", "40.56"],
                ["ConvS2S ensemble", "26.36", "41.29"],
                ["Transformer base", "27.3", "38.1"],
                ["Transformer big", "28.4", "41.8"],
              ],
              numeric: [1, 2], highlight: 3,
            },
            { kind: "p", text: "The French result requires an explicit source caveat. The abstract and Table 2 report ==41.8==, but the prose of Section 6.1 reports 41.0. Both exceed the listed best earlier single-model score of 40.56, yet only 41.8 exceeds the listed 41.29 ensemble." },
          ],
        },
      },
      {
        title: "Not just the numbers: what they actually show",
        paper: {
          src: "showcase/paper-table-3.png",
          alt: "Paper Table 3: ablations of the Transformer architecture",
          caption: "Paper · p. 9 · Table 3",
          box: [73, 81, 89.5, 88.5],
        },
        note: {
          path: "Experimental Evidence › Component ablations",
          blocks: [
            {
              kind: "table",
              headers: ["Family", "Change from base, unless stated", "Dev perplexity", "Dev BLEU"],
              rows: [
                ["Reference", "6 layers, width 512, 8 heads, key and value width 64", "4.92", "25.8"],
                ["A", "1 head, key and value width 512", "5.29", "24.9"],
                ["D", "Dropout 0", "5.77", "24.6"],
                ["D", "Label smoothing 0", "4.67", "25.3"],
              ],
              numeric: [2, 3], highlight: 3,
            },
            { kind: "p", text: "Removing dropout worsens both development perplexity and BLEU. Removing label smoothing ==improves perplexity from 4.92 to 4.67 but worsens BLEU from 25.8 to 25.3==, showing why probability fit cannot replace the task metric. [Table 3 B-D]" },
          ],
        },
      },
      ],
    },
    wiki: {
      title: "From Paper to Wiki",
      body:
        "DeepPaperNote reads each paper deeply and saves it well. Three optional companion skills look after your vault as a whole.",
      coreLabel: "Core",
      coreTree: "<your papers folder>/\n└── NLP/\n    └── Attention_Is_All_You_Need/\n        ├── Attention_Is_All_You_Need.en.md\n        └── images/\n            ├── figure_1.png\n            └── table_2.png",
      skills: [
        {
          name: "deeppapernote",
          body:
            "Deep-reads one paper and saves an illustrated note into your vault, linked to the other papers you have read.",
          phrase: "Generate a deep-reading note for this paper: <paper>",
        },
        {
          name: "research-memory",
          body:
            "Records the research directions you are working on and follows them as you read. With it, each note's Takeaways are written against your directions, so the next note knows you better.",
          phrase: "Build my research memory",
        },
        {
          name: "organize-wiki",
          body:
            "Sorts out your domain categories, moves papers filed under the wrong domain, and fixes their tags. The categories it settles guide where new papers are filed.",
          phrase: "Organize my paper library",
        },
        {
          name: "paper-glossary",
          body:
            "Turns a paper's key concepts into reusable term notes linked back into the text. The same term in different papers points to the same note.",
          phrase: "Build glossary notes for this paper",
        },
      ],
      rhythmLabel: "A good rhythm",
      rhythm: [
        "Read a few papers",
        "Once notes pile up, build a research memory",
        "When categories drift, organize the vault",
      ],
    },
    install: {
      title: "Install the skill. Hand it one paper.",
      body:
        "A title, DOI, arXiv ID, or local PDF is enough. The first time, it asks only two things: which language to write in, and where to save.",
      updateLabel: "Already installed? See how to update →",
      updateHref: "https://github.com/917Dhj/DeepPaperNote#4-update-to-a-new-version",
      commandsLabel: "Install commands",
      tabs: [
        {
          id: "claude",
          label: "Claude Code",
          comment: "# 1. Install",
          command: "claude plugin marketplace add 917Dhj/DeepPaperNote\nclaude plugin install deeppapernote@deeppapernote",
        },
        {
          id: "skills",
          label: "Codex & other agents",
          comment: "# 1. Install",
          command: "npx skills add 917Dhj/DeepPaperNote",
        },
      ],
      steps: [
        { comment: "# 2. Install the PDF dependency", command: "python3 -m pip install PyMuPDF" },
        { comment: "# 3. Read a paper", command: "/deeppapernote https://arxiv.org/abs/1706.03762" },
      ],
    },
    closingNote:
      "Thanks for reading, using, and supporting DeepPaperNote. May your paper-reading days be a little clearer, calmer, and more rewarding.",
    footer: {
      by: "by",
      github: "GitHub",
      releases: "Releases",
      issues: "Issues",
    },
  },
  zh: {
    lang: "zh-CN",
    title: "DeepPaperNote｜把一篇复杂的论文，写成值得长期保留的精读笔记",
    description:
      "把一篇论文交给 DeepPaperNote，它会读完全文，写成图文并茂的精读笔记，存进你的 Obsidian 知识库，并连到你读过的其他论文。",
    brandHomeLabel: "DeepPaperNote 首页",
    navLabel: "页面导航",
    headerActionsLabel: "页头操作",
    languageSwitchLabel: "语言",
    themeSwitchLabel: "颜色主题",
    githubStarsLabel: "DeepPaperNote GitHub 星标",
    starsFallback: "星标",
    starsAriaTemplate: "GitHub 已收获 {count} 个 Star",
    installLabel: "安装",
    nav: {
      features: "特点",
      showcase: "笔记",
      wiki: "知识库",
      install: "安装",
    },
    languageNames: {
      en: "English",
      zh: "简体中文",
    },
    theme: {
      system: "系统",
      light: "亮色",
      dark: "暗色",
      systemLabel: "跟随系统",
      lightLabel: "切换为亮色",
      darkLabel: "切换为暗色",
    },
    hero: {
      badge: "v3.0.0 已发布",
      title: "把一篇复杂的论文，写成值得长期保留的精读笔记。",
      body:
        "DeepPaperNote 是一个 Agent Skill，可以运行在 Claude Code、Codex 等任何支持 skill 的 Agent 里。把一篇论文交给它，它会读完全文，写成一篇图文并茂的精读笔记，存进你的 Obsidian 知识库，并连到你读过的其他论文上。",
      bodyStrong: "每读一篇，你的学术 Wiki 就长大一点。",
      actionsLabel: "主要操作",
      install: "安装",
      github: "查看 GitHub",
      demoLabel: "DeepPaperNote 产品演示动画",
      demoTitle: "DeepPaperNote 产品演示动画",
    },
    features: {
      title: "为什么是 DeepPaperNote",
      body: "从一句话开始，到一篇你信得过、用得上的笔记。",
      cards: [
        {
          tag: "上手",
          title: "一句话，一篇笔记",
          body:
            "不用学提示词，也不用配模板。给它标题、DOI、arXiv ID 或 PDF，找原文、读全文、提取图表、存进知识库，全部自动完成。",
          className: "card-yellow",
        },
        {
          tag: "专业",
          title: "像领域专家一样读",
          body:
            "从 CS/AI 到医学、心理乃至人文，10 种论文类型各有一套专门的读法，参考了 50 多份审稿指南和报告规范，并在 34 篇真实论文上反复检验。",
          className: "card-mint",
        },
        {
          tag: "可信",
          title: "写得准，写得全",
          body:
            "结论都能在原文找到出处，数字直接取自正文和表格，每个主要实验都会写到。保存前要经过独立审阅和严格的质量审查，读不到全文时绝不凭空编写。",
          className: "card-rose",
        },
        {
          tag: "图文",
          title: "图、表、公式融进正文",
          body:
            "图表从原文裁剪出来，放在笔记讨论它的地方；公式在 Obsidian 里直接渲染，读笔记不用再翻 PDF。",
          className: "card-yellow",
        },
        {
          tag: "知识库",
          title: "越用越懂你的知识库",
          body:
            "新笔记会自动链接库里的相关论文，归入你已有的领域文件夹。记下你的研究方向后，“阅读收获”会告诉你，这篇论文对你的研究有什么用。",
          className: "card-mint",
        },
      ],
    },
    showcase: {
      title: "这份笔记，本身就是产品。",
      body:
        "笔记里的每条结论，都能追溯到原文的某一页、某张图表。",
      paperLabel: "原文",
      noteLabel: "笔记",
      pairs: [
      {
        title: "原图嵌进正文，旁边就是解读",
        paper: {
          src: "showcase/paper-figure-1.png",
          alt: "论文 Figure 1：Transformer 模型架构",
          caption: "原文 · 第 3 页 · Figure 1",
          box: [63, 84.5, 95, 93],
        },
        note: {
          path: "方法 › 方法流程",
          blocks: [
            { kind: "caption", text: "论文原图编号：Fig. 1。编码器与解码器的完整结构，展示位置输入、三类注意力、残差和输出路径。" },
            { kind: "p", text: "训练和推理共享架构，但目标前缀的来源不同。==训练使用已知的正确目标前缀==，可以同时计算各目标位置的预测；推理只拥有已经生成的前缀，必须产生新词后才能继续。这一区别决定了本文的并行收益首先体现在训练，而不是消除生成的逐步依赖。" },
          ],
        },
      },
      {
        title: "数字取自原文，连矛盾也写出来",
        paper: {
          src: "showcase/paper-table-2.png",
          alt: "论文 Table 2：BLEU 分数与训练成本",
          caption: "原文 · 第 8 页 · Table 2",
          box: [55.5, 89.5, 63.5, 99],
        },
        note: {
          path: "实验证据 › 翻译主结果",
          blocks: [
            {
              kind: "table",
              headers: ["模型", "英德 BLEU", "英法 BLEU"],
              rows: [
                ["`MoE`", "26.03", "40.56"],
                ["`ConvS2S` 集成", "26.36", "41.29"],
                ["`Transformer` 基础模型", "27.3", "38.1"],
                ["`Transformer` 大模型", "28.4", "41.8"],
              ],
              numeric: [1, 2], highlight: 3,
            },
            { kind: "p", text: "**英法分数在这份本地版本中存在内部不一致。** 摘要与表 2 给出大模型 ==`41.8`==，第 6.1 节正文写成 `41.0`。……若采用 `41.0`，仍超过表中最佳单模型 `40.56`，但不超过最佳集成 `41.29`。" },
          ],
        },
      },
      {
        title: "不只抄数字，还讲清它说明了什么",
        paper: {
          src: "showcase/paper-table-3.png",
          alt: "论文 Table 3：Transformer 架构变体的消融结果",
          caption: "原文 · 第 9 页 · Table 3",
          box: [73, 81, 89.5, 88.5],
        },
        note: {
          path: "实验证据 › 组件消融",
          blocks: [
            {
              kind: "table",
              headers: ["消融组", "改动，其他项沿用基础模型", "开发集 PPL", "开发集 BLEU"],
              rows: [
                ["基准", "6 层、512 维、8 头", "4.92", "25.8"],
                ["A", "1 头，每头键／值维度 512／512", "5.29", "24.9"],
                ["D", "丢弃率 0", "5.77", "24.6"],
                ["D", "标签平滑 0", "4.67", "25.3"],
              ],
              numeric: [2, 3], highlight: 3,
            },
            { kind: "p", text: "正则化的结果说明，概率拟合指标和最终翻译质量不总是一致。去掉丢弃法下降 `1.2 BLEU`；去掉标签平滑时，==困惑度从 `4.92` 改善到 `4.67`，翻译成绩却从 `25.8` 降到 `25.3`==。如果只按困惑度挑模型，会错过这个任务指标上的差异。" },
          ],
        },
      },
      ],
    },
    wiki: {
      title: "从论文到知识库",
      body:
        "DeepPaperNote 负责把每一篇论文读透、存好。另外三个配套 skill 都是可选的，它们照看的是整个知识库。",
      coreLabel: "核心",
      coreTree: "<你的论文目录>/\n└── 自然语言处理/\n    └── Attention_Is_All_You_Need/\n        ├── Attention_Is_All_You_Need.zh-CN.md\n        └── images/\n            ├── figure_1.png\n            └── table_2.png",
      skills: [
        {
          name: "deeppapernote",
          body:
            "精读一篇论文，写成图文并茂的笔记存进知识库，并连到你读过的其他论文上。",
          phrase: "给这篇论文生成深度笔记：<论文>",
        },
        {
          name: "research-memory",
          body:
            "记下你正在做的研究方向，并随着你读的论文持续跟进。有了它，“阅读收获”会对照你的方向来写，下一篇笔记会更懂你。",
          phrase: "建立我的研究记忆",
        },
        {
          name: "organize-wiki",
          body:
            "理清领域分类，把放错领域的论文归位，修正领域标签。整理好的分类会成为之后归档新论文的依据。",
          phrase: "整理我的知识库",
        },
        {
          name: "paper-glossary",
          body:
            "把论文里的关键概念整理成可复用的术语笔记，并链接回正文。不同论文里的同一个术语，都指向同一篇术语笔记。",
          phrase: "给这篇论文建术语笔记",
        },
      ],
      rhythmLabel: "推荐的节奏",
      rhythm: [
        "先读几篇论文",
        "库里有了笔记，建一份研究记忆",
        "论文多了、分类乱了，整理一次知识库",
      ],
    },
    install: {
      title: "装好这个 Skill，丢给它一篇论文就行。",
      body:
        "标题、DOI、arXiv ID 或本地 PDF 都可以。第一次用时它只问两件事：笔记用什么语言，存到哪里。",
      updateLabel: "已经装过？更新方法见 README →",
      updateHref: "https://github.com/917Dhj/DeepPaperNote/blob/main/README.zh-CN.md#4-更新到新版本",
      commandsLabel: "安装命令",
      tabs: [
        {
          id: "claude",
          label: "Claude Code",
          comment: "# 1. 安装",
          command: "claude plugin marketplace add 917Dhj/DeepPaperNote\nclaude plugin install deeppapernote@deeppapernote",
        },
        {
          id: "skills",
          label: "Codex 及其他 Agent",
          comment: "# 1. 安装",
          command: "npx skills add 917Dhj/DeepPaperNote",
        },
      ],
      steps: [
        { comment: "# 2. 安装 PDF 依赖", command: "python3 -m pip install PyMuPDF" },
        { comment: "# 3. 开始读论文", command: "/deeppapernote https://arxiv.org/abs/1706.03762" },
      ],
    },
    closingNote:
      "感谢你阅读、使用和支持 DeepPaperNote。愿你的每一次论文精读，都更清晰、更从容，也更有收获。",
    footer: {
      by: "by",
      github: "GitHub",
      releases: "版本发布",
      issues: "问题反馈",
    },
  },
};
