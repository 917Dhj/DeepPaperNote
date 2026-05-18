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
          tag: "Result",
          title: "A reading note, not a recap",
          body:
            "The note preserves the paper's question, method backbone, key results, limitations, and reusable research context.",
          className: "card-yellow",
        },
        {
          tag: "Evidence",
          title: "Claims follow the source",
          body:
            "Metadata, sections, captions, formulas, and numeric claims are gathered before the final synthesis begins.",
          className: "card-mint",
        },
        {
          tag: "Figures",
          title: "Figure-aware by default",
          body:
            "Major figures, tables, and formulas stay attached to the reasoning they support, so visual evidence remains part of the deep read.",
          className: "card-rose",
        },
      ],
      noteOutlineLabel: "Generated note outline example",
      noteOutlinePanel: "Generated structure",
      noteOutlineTitle: "DeepPaperNote output",
      noteOutlineItems: [
        "Abstract translation",
        "Novelty",
        "Method backbone",
        "Key results",
        "Deep analysis",
      ],
      visualPanel: "Visual evidence",
      visualTitle: "Figures, tables, and formulas stay with the claims they support.",
      visualBody:
        "DeepPaperNote keeps visual and mathematical evidence inside the Obsidian note, close to the reasoning built from it.",
      visualArtifactLabel: "Visual evidence note mockup",
      artifactTitle: "Fig. 2 Model architecture overview",
      artifactChip: "caption matched",
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
      tableLabel: "Evidence table mockup",
      tableHeaders: ["Evidence", "Source", "Role"],
      tableRows: [
        ["Architecture diagram", "Fig. 2", "Model flow"],
        ["Attention equation", "Eq. 1", "Core math"],
        ["Ablation table", "Table 4", "Result check"],
      ],
    },
    pipeline: {
      title: "A disciplined path from paper to note.",
      body:
        "Scripts prepare structured evidence. The model does the reading. The final note is linted, reviewed, and saved where your research actually lives.",
      steps: [
        { title: "Resolve", body: "Pick one canonical paper identity." },
        { title: "Evidence", body: "Extract sections, captions, metrics, and context." },
        { title: "Figures", body: "Plan major figure and table placeholders first." },
        { title: "Synthesis", body: "Turn the bundle into a deep-reading note." },
        { title: "Lint", body: "Check structure, style, and note completeness." },
        { title: "Save", body: "Write to an Obsidian-style paper folder." },
      ],
    },
    install: {
      title: "Install the skill. Hand it one paper.",
      body: "Keep the website out of the skill package. Keep the workflow focused on the note.",
      commandsLabel: "Install commands",
      commands: [
        "npx skills add 917Dhj/DeepPaperNote",
        "python3 -m pip install PyMuPDF",
        "Use DeepPaperNote on this paper: https://arxiv.org/abs/1706.03762",
      ],
    },
    footer: {
      by: "by",
      github: "GitHub",
      releases: "Releases",
      issues: "Issues",
    },
  },
  zh: {
    lang: "zh-CN",
    title: "DeepPaperNote | 面向 Obsidian 的证据优先论文笔记",
    description:
      "DeepPaperNote 将一篇高密度研究论文转化为值得长期保存的证据优先 Obsidian 笔记。",
    brandHomeLabel: "DeepPaperNote 首页",
    navLabel: "页面分区",
    headerActionsLabel: "顶部操作",
    languageSwitchLabel: "语言",
    themeSwitchLabel: "颜色主题",
    githubStarsLabel: "DeepPaperNote GitHub 星标",
    starsFallback: "星标",
    starsAriaTemplate: "GitHub 上的 {count} 个星标",
    installLabel: "安装",
    nav: {
      showcase: "展示",
      pipeline: "流程",
      install: "安装",
    },
    languageNames: {
      en: "英文",
      zh: "中文",
    },
    theme: {
      system: "系统",
      light: "亮色",
      dark: "暗色",
      systemLabel: "使用系统颜色主题",
      lightLabel: "使用亮色主题",
      darkLabel: "使用暗色主题",
    },
    hero: {
      title: "把一篇高密度论文，变成值得长期保存的 Obsidian 笔记。",
      body:
        "DeepPaperNote 是为研究者准备的证据优先深读流程，不止停留在摘要式总结。",
      actionsLabel: "主要操作",
      install: "使用 npx 安装",
      github: "查看 GitHub",
      demoLabel: "DeepPaperNote 动态产品演示",
      demoTitle: "DeepPaperNote 动态产品演示",
    },
    showcase: {
      title: "最终笔记就是产品本身。",
      body:
        "DeepPaperNote 围绕你真正会保存的笔记构建：结构清晰、证据明确、关注图表，并适合长期放进 Obsidian 知识库。",
      cards: [
        {
          tag: "结果",
          title: "是深读笔记，不是复述摘要",
          body:
            "笔记会保留论文的问题意识、方法主线、关键结果、局限性，以及可复用的研究上下文。",
          className: "card-yellow",
        },
        {
          tag: "证据",
          title: "论断跟着原文证据走",
          body:
            "在最终综合之前，先收集元数据、章节、图注、公式和数值论断，避免凭空生成结论。",
          className: "card-mint",
        },
        {
          tag: "图表",
          title: "默认关注图表证据",
          body:
            "关键图、表格和公式会跟它们支撑的推理保持关联，让视觉证据成为深读的一部分。",
          className: "card-rose",
        },
      ],
      noteOutlineLabel: "生成笔记大纲示例",
      noteOutlinePanel: "生成结构",
      noteOutlineTitle: "DeepPaperNote 输出",
      noteOutlineItems: ["原文摘要翻译", "创新点", "方法主线", "关键结果", "深度分析"],
      visualPanel: "视觉证据",
      visualTitle: "图、表和公式会留在它们支撑的论断旁边。",
      visualBody:
        "DeepPaperNote 会把视觉和数学证据保留在 Obsidian 笔记中，并贴近由这些证据展开的推理。",
      visualArtifactLabel: "视觉证据笔记示意",
      artifactTitle: "图 2 模型架构概览",
      artifactChip: "图注已匹配",
      figureMapLabel: "模型架构图示意",
      stages: {
        input: "输入 tokens",
        embedding: "嵌入",
        attention: "多头注意力",
        residual: "残差 + 归一化",
        feedForward: "前馈网络",
        output: "输出状态",
      },
      formulaLabel: "注意力公式",
      tableLabel: "证据表格示意",
      tableHeaders: ["证据", "来源", "作用"],
      tableRows: [
        ["架构图", "图 2", "模型流程"],
        ["注意力公式", "式 1", "核心数学"],
        ["消融表格", "表 4", "结果校验"],
      ],
    },
    pipeline: {
      title: "从论文到笔记，有一条克制的路径。",
      body:
        "脚本准备结构化证据，模型负责深读，最终笔记经过 lint、复核，并保存到你的研究知识库里。",
      steps: [
        { title: "解析", body: "确定一篇论文的规范身份。" },
        { title: "证据", body: "提取章节、图注、指标和上下文。" },
        { title: "图表", body: "先规划关键图表和表格占位。" },
        { title: "综合", body: "把证据包转化为深读笔记。" },
        { title: "检查", body: "检查结构、风格和笔记完整度。" },
        { title: "保存", body: "写入 Obsidian 风格的论文文件夹。" },
      ],
    },
    install: {
      title: "安装这个 skill，然后交给它一篇论文。",
      body: "网站不进入 skill 安装包，工作流始终聚焦在最终笔记。",
      commandsLabel: "安装命令",
      commands: [
        "npx skills add 917Dhj/DeepPaperNote",
        "python3 -m pip install PyMuPDF",
        "用 DeepPaperNote 阅读这篇论文：https://arxiv.org/abs/1706.03762",
      ],
    },
    footer: {
      by: "作者",
      github: "GitHub",
      releases: "发布",
      issues: "问题",
    },
  },
};
