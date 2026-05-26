export type Locale = "en" | "zh";

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
    showcase: string;
    pipeline: string;
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
    title: string;
    body: string;
    actionsLabel: string;
    install: string;
    github: string;
    demoLabel: string;
    demoTitle: string;
  };
  showcase: {
    title: string;
    body: string;
    cards: Array<{
      tag: string;
      title: string;
      body: string;
      className: string;
    }>;
    noteOutlineLabel: string;
    noteOutlinePanel: string;
    noteOutlineTitle: string;
    noteOutlineItems: string[];
    visualPanel: string;
    visualTitle: string;
    visualBody: string;
    visualArtifactLabel: string;
    artifactTitle: string;
    artifactChip: string;
    figureMapLabel: string;
    stages: {
      input: string;
      embedding: string;
      attention: string;
      residual: string;
      feedForward: string;
      output: string;
    };
    formulaLabel: string;
    tableLabel: string;
    tableHeaders: string[];
    tableRows: Array<[string, string, string]>;
  };
  pipeline: {
    title: string;
    body: string;
    steps: Array<{
      title: string;
      body: string;
    }>;
  };
  install: {
    title: string;
    body: string;
    commandsLabel: string;
    commands: string[];
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
    title: "DeepPaperNote | Evidence-first paper notes for Obsidian",
    description:
      "DeepPaperNote turns one dense research paper into an evidence-first Obsidian note worth keeping.",
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
      showcase: "Showcase",
      pipeline: "Pipeline",
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
      title: "Turn one dense paper into an Obsidian note worth keeping.",
      body:
        "DeepPaperNote is an evidence-first reading workflow for researchers who want more than an abstract summary.",
      actionsLabel: "Primary actions",
      install: "Install with npx",
      github: "View GitHub",
      demoLabel: "DeepPaperNote animated product demo",
      demoTitle: "DeepPaperNote animated product demo",
    },
    showcase: {
      title: "The output is the product.",
      body:
        "DeepPaperNote is built around the note you keep: structured, evidence-aware, figure-conscious, and ready for a long-term Obsidian vault.",
      cards: [
        {
          tag: "Deep notes",
          title: "Deep notes, not recap",
          body:
            "The note tracks what the paper proves, what it does not prove, which experiments matter, and where the conclusions are bounded.",
          className: "card-yellow",
        },
        {
          tag: "Tables",
          title: "Clear result tables",
          body:
            "Core comparisons across models, datasets, tasks, settings, or metrics become compact Markdown tables with interpretation after the numbers.",
          className: "card-mint",
        },
        {
          tag: "Images",
          title: "Image-first figures",
          body:
            "Usable figure and table candidates are embedded as real images; placeholders stay for missing, broken, or mismatched visuals.",
          className: "card-rose",
        },
      ],
      noteOutlineLabel: "Generated note outline example",
      noteOutlinePanel: "Generated structure",
      noteOutlineTitle: "DeepPaperNote output",
      noteOutlineItems: [
        "Core metadata",
        "Evidence-backed claims",
        "Compact result table",
        "Image-first figures",
        "Deep analysis",
      ],
      visualPanel: "Results, figures, and formulas",
      visualTitle: "Comparisons, visuals, and math stay close to the analysis.",
      visualBody:
        "Core comparisons become compact Markdown tables, while usable visuals and formulas stay near the claims they support.",
      visualArtifactLabel: "Visual evidence note mockup",
      artifactTitle: "Fig. 2 Architecture + Table 4 Results",
      artifactChip: "image inserted",
      figureMapLabel: "Model architecture figure mockup",
      stages: {
        input: "Input tokens",
        embedding: "Embedding",
        attention: "Multi-head attention",
        residual: "residual + norm",
        feedForward: "Feed-forward",
        output: "Output states",
      },
      formulaLabel: "Attention formula",
      tableLabel: "Compact result table mockup",
      tableHeaders: ["Setting", "Metric", "What it means"],
      tableRows: [
        ["Main model", "+4.8 F1", "Best overall trade-off"],
        ["Ablation", "-2.1 F1", "Module matters"],
        ["Baseline", "73.2%", "Reference point"],
      ],
    },
    pipeline: {
      title: "A disciplined path from paper to note.",
      body:
        "Scripts prepare structured evidence. The model does the reading. The final note is linted, reviewed, and saved where your research actually lives.",
      steps: [
        { title: "Resolve", body: "Pick one canonical paper identity." },
        { title: "Source", body: "Read from source sections and metadata, not just title or abstract." },
        { title: "Plan", body: "Decide the central claims, key experiments, and analysis focus." },
        { title: "Results & figures", body: "Turn comparisons into tables and embed usable visuals." },
        { title: "Review", body: "Check grounding, analytical depth, and readability before saving." },
        { title: "Save", body: "Write to an Obsidian-style paper folder." },
      ],
    },
    install: {
      title: "Install the skill. Hand it one paper.",
      body: "A title, DOI, URL, arXiv link, or local PDF is enough to start a deep-reading note.",
      commandsLabel: "Install commands",
      commands: [
        "npx skills add 917Dhj/DeepPaperNote",
        "python3 -m pip install PyMuPDF",
        "Turn this paper into an Obsidian note: https://arxiv.org/abs/1706.03762",
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
    title: "DeepPaperNote｜为 Obsidian 打造的证据型论文精读笔记",
    description:
      "DeepPaperNote 把一篇复杂的论文，整理成一份你愿意长期保留的 Obsidian 精读笔记。",
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
      showcase: "效果",
      pipeline: "工作流",
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
      title: "把一篇复杂的论文，整理成一份真正值得保留的 Obsidian 精读笔记",
      body:
        "DeepPaperNote 是给研究者用的论文精读工作流——先取证、再写作，不只是把摘要复述一遍。",
      actionsLabel: "主要操作",
      install: "使用 npx 安装",
      github: "查看 GitHub",
      demoLabel: "DeepPaperNote 产品演示动画",
      demoTitle: "DeepPaperNote 产品演示动画",
    },
    showcase: {
      title: "这份笔记，本身就是产品。",
      body:
        "DeepPaperNote 围绕“你真正会留下的那份笔记”来设计：结构清晰、有据可查、图表完整，适合长期放进 Obsidian 知识库。",
      cards: [
        {
          tag: "深度",
          title: "是精读笔记，不是摘要复述",
          body:
            "笔记会解释论文证明了什么、还没证明什么、哪些实验最关键，以及结论能走到哪里。",
          className: "card-yellow",
        },
        {
          tag: "表格",
          title: "结果表格更清楚",
          body:
            "多个模型、数据集、任务、设置或指标的核心比较，会整理成紧凑 Markdown 表格，并解释数字含义。",
          className: "card-mint",
        },
        {
          tag: "图像",
          title: "图像优先插入",
          body:
            "可用图表直接嵌入为真实图片；缺失、破损或不匹配时才保留占位符。",
          className: "card-rose",
        },
      ],
      noteOutlineLabel: "生成笔记大纲示例",
      noteOutlinePanel: "输出结构",
      noteOutlineTitle: "DeepPaperNote 输出",
      noteOutlineItems: ["核心信息", "证据支撑的解析", "结果表格", "图像优先", "精读分析"],
      visualPanel: "结果、图表与公式",
      visualTitle: "核心比较、可用图像和公式都贴近分析保留。",
      visualBody:
        "核心比较会整理成紧凑 Markdown 表格，可用图表和公式会留在它们支撑的分析旁边。",
      visualArtifactLabel: "视觉证据笔记示意",
      artifactTitle: "图 2 架构 + 表 4 结果",
      artifactChip: "图片已嵌入",
      figureMapLabel: "模型架构图示意",
      stages: {
        input: "输入 Token",
        embedding: "嵌入",
        attention: "多头注意力",
        residual: "残差 + 归一化",
        feedForward: "前馈网络",
        output: "输出状态",
      },
      formulaLabel: "注意力公式",
      tableLabel: "紧凑结果表格示意",
      tableHeaders: ["设置", "指标", "说明"],
      tableRows: [
        ["主模型", "+4.8 F1", "整体权衡最好"],
        ["消融设置", "-2.1 F1", "模块确实有贡献"],
        ["基线", "73.2%", "对照参照点"],
      ],
    },
    pipeline: {
      title: "从论文到笔记，走一条严谨的流程。",
      body:
        "脚本负责取证，模型负责精读；最终笔记会经过 lint 校验和可读性复核，再写进你的研究知识库。",
      steps: [
        { title: "解析", body: "锁定这篇论文的唯一身份。" },
        { title: "原文", body: "从原文章节和元数据取证，不只看标题或摘要。" },
        { title: "规划", body: "确定核心结论、关键实验和分析重点。" },
        { title: "结果与图表", body: "把比较整理成表格，并嵌入可用图像。" },
        { title: "复核", body: "保存前检查证据、分析深度和可读性。" },
        { title: "保存", body: "按 Obsidian 的习惯，归档到对应的论文文件夹。" },
      ],
    },
    install: {
      title: "装好这个 Skill，丢给它一篇论文就行。",
      body: "论文标题、DOI、URL、arXiv 链接或本地 PDF 都可以，交给 agent 就能开始生成精读笔记。",
      commandsLabel: "安装命令",
      commands: [
        "npx skills add 917Dhj/DeepPaperNote",
        "python3 -m pip install PyMuPDF",
        "把这篇文章整理成 Obsidian 笔记：https://arxiv.org/abs/1706.03762",
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
