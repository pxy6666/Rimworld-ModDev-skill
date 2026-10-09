# RimWorld ModDev Skill

给 Cursor、Codex 等支持 Agent Skills 的代理使用的 RimWorld mod 开发流程。它帮助代理把玩家需求转换为可查证的 Def、XML、C# 和资源实现，也支持基于其他 mod 的调用、衍生与兼容补丁。

核心顺序是：**先确认用途与真实类型，再查模板和默认值；真正未定的玩法数值与资源才交给玩家或 CLI 决定。**

当前版本：**1.1.0**。项目仍在改进，技能内容包含 AI 辅助编写；静态检查、编译成功和游戏内验证分别记录，不能保证所有客户端、游戏版本和 mod 组合都已验证。

## 选择 Basic 或 Image

| 版本 | 目录 / Cursor 插件名 | 适用情况 |
| --- | --- | --- |
| Basic | [basic/](basic/) / `rimworld-moddev-basic` | 使用已有、外部提供或允许复用的素材，不接入平台生图流程 |
| Image | [image/](image/) / `rimworld-moddev-image` | 需要外观需求 → 资源规格 → 生图 → 导入 PNG → 视觉检查 → 绑定引用 → 游戏验收 |

两版都包含相同的五个技能、需求/计划/制作/复查流程与资源检查。Image 需要会话中实际可用的图像工具，或用户选定且可调用的外部来源；安装技能不会自动获得生图服务。

**同一工程/客户端只启用一版。** 两版技能同名，同时安装可能出现重复入口。切换时先移除或禁用旧版；手动安装须替换整套五个技能，避免残留 Image 专属文件。

## 五个技能

| 技能 | 什么时候用 |
| --- | --- |
| `rimworld-help` | 第一次使用、目标尚不明确，或不知道下一步 |
| `rimworld-setup` | 检查游戏路径、编译环境、检索/MCP 和必要工具能力 |
| `rimworld-mod` | 制作/修改内容、C# 系统、界面、上游整合，或连续添加功能 |
| `rimworld-debug` | 排查加载、XML、行为、兼容、存档、性能或版本迁移问题 |
| `rimworld-release` | 核对成果、依赖、资源来源并准备发行包；明确要求时才上传工坊 |

## 安装

### Cursor

本仓库保留 `.cursor-plugin/marketplace.json` 及 Basic/Image 两个插件清单。在支持仓库导入的 Cursor 入口中填入本仓库地址，再只安装其中一版。插件从 Customize 管理；团队市场可由管理员通过 Dashboard → Plugins & MCPs → Add Marketplace → Import from Repo 导入。入口因客户端版本或账户而异，找不到仓库导入时可用下面的手动方式。[Cursor 插件文档](https://cursor.com/docs/plugins)

安装后可在 Agent 对话输入 `/rimworld-help` 或 `/rimworld-mod`，也可描述目标让代理匹配技能。[Cursor 技能文档](https://cursor.com/docs/skills)

### Codex / Cursor 手动安装

克隆或下载本仓库，选择 `basic/skills/` 或 `image/skills/`，把其中**五个技能文件夹整体复制**到目标 mod 工程的 `.agents/skills/`：

```text
YourMod/
└── .agents/skills/
    ├── rimworld-help/
    ├── rimworld-setup/
    ├── rimworld-mod/
    ├── rimworld-debug/
    └── rimworld-release/
```

复制 `SKILL.md` 时保留同目录的 `references/`，不要只复制入口文件或把 Basic/Image 两个父目录一起放进去。已有同名技能先确认来源，不直接覆盖自己的修改。

Codex 的项目级技能路径是 `.agents/skills/`，用户级路径为 `~/.agents/skills/`；CLI/IDE 可通过 `/skills` 查看或用 `$rimworld-help` 指定技能。更新未显示时重新发现或重启客户端。[OpenAI 技能文档](https://learn.chatgpt.com/docs/build-skills)

Cursor 也支持项目级 `.agents/skills/` 与 `.cursor/skills/`。两客户端在同一工程使用时可共享前者。单纯打开下载后的本仓库，不等于把技能安装进你的 mod 工程。[Cursor 技能目录](https://cursor.com/docs/skills)

本仓库的插件清单是 Cursor 格式；这里的 Codex 用法是技能文件夹安装，不代表已经提供 Codex/ChatGPT 原生插件。其他平台需支持相应技能加载，并具有工程文件访问与执行能力。

## 第一次使用

在实际 mod 工程中开始会话。提供已有项目位置、RimWorld 版本、游戏安装路径及有关 DLC；新工程也可以让代理先整理身份和结构。需要参考上游时提供其名称、路径或仓库，以及你想调用、衍生还是修正什么。

不知道环境是否准备好，可先说：

```text
请使用 rimworld-help。我要为 RimWorld 1.6 制作一个独立 mod。
先检查当前工程与所需环境，说明缺什么，再带我整理需求和计划。
```

明确制作目标时可以这样开始：

```text
请使用 rimworld-mod，制作一把可以直接远程投掷的吸血飞刀。
命中造成伤害后为使用者恢复生命，贴图复用原版。
先确认实际攻击类型与实现路径，再给我计划；不要立即制作。
伤害由我选择，其余未定数值参考原版决定，使用混合模式。
```

无需自己填写内部类名、全部 XML 或完整美术规格。代理负责技术查证；玩法取舍、必要资源来源和未定数值按你选的模式解决。

## 制作过程

1. 分解需求，判断内容的真实用途、类型、触发与执行链，初步判断是否需要 C#。
2. 对关键不确定方向给玩家选项，分析原版或上游 mod 提供的接口。
3. 复用有效证据，优先 MCP 小查询；必要时核对 XML、源码/DLL 或运行时 Def，形成配置契约与记录。
4. 展示经过技术自检的具体计划，确认计划与制作模式后进入制作；已有明确同意或自主规划实施委托可沿用。
5. 每个功能块核对类型/契约、补真正缺项、准备必要资源、制作并复查。
6. 检查整体获取、触发、组合与相关存档/视觉，准确报告通过、失败或未验证项。

制作模式只处理真正未定项：

| 模式 | 谁决定 |
| --- | --- |
| 用户控制 | 代理提出有依据的候选与影响，玩家选择 |
| CLI 决定 | 在授权范围内参照同用途、匹配版本的原版或已选上游，并记录理由 |
| 混合 | 玩家锁定关键项，其余明确委托代理 |

已给定的合法 `0`/`false` 不算缺项；已满足目标的继承/默认不用重复填。字段常见不等于必填，少见不等于无效。“数值你定”也不自动代替整个计划确认。

### 六种制作范围

| 范围 | 允许的主要工作 |
| --- | --- |
| L1 | 原版/已有自身内容的局部数据、贴图、声音或文案修改 |
| L2 | 原版/DLC XML 内容，不新增自己的 DLL |
| L3 | 原版/DLC C# 逻辑、系统或显示功能，Def 按需出现 |
| L4 | 基于上游的 XML/资源引用、衍生或补丁 |
| L5 | 调用上游代码、衍生逻辑或 C# 兼容补丁 |
| L6 | 在授权内直接编辑上游工程 |

它们限定修改范围，不是必须逐级执行的六步。完整 mod 可以混合多个功能块；库型与内容型 mod 都可能提供可调用的代码或可引用的配置。

### 连续添加内容

后续可以直接要求“继续上次功能”或“给这个 mod 增加一个工作台”。代理从项目概览、功能记录、引用索引和检查点恢复，只补查受影响项，不每次重走全部查询。小项目可共用一份短记录。

每次增量完成后交付并等待新需求。要求中止某部分时保存停止位置与遗留项；再次继续时核对实际文件和证据。项目文档不替代真实实现，来源/版本变化会使相关证据失效。

## 工具与资源准备

按任务使用 [RimSage](https://github.com/realloon/RimSage)、[RimSearcher](https://github.com/kearril/RimSearcher)、[DecompilerServer](https://github.com/pardeike/DecompilerServer) 或已有检索工具，不要求同时安装全部能力。原始 XML、源码/DLL 和运行时 Def 各回答不同问题；MCP 不可用或版本不匹配时记录回退原因及剩余缺口。

游戏路径与相关程序集由使用方提供；C# 任务才准备适合目标游戏/上游的构建环境。贴图、声音和文本只请求本功能真正需要的部分，允许经确认的原版/上游运行时资源引用。Image 来源偏好可记录在项目中，实际能否生成还要检查当前工具。

**此仓库分发技能与必要参考页，不含游戏文件、编译器、工程 CLI、研究报告、统计数据库、日志、本机配置或密钥。** 技能提到的 `tools/preflight.ps1`、`tools/mod.ps1`、统计查询或资源导入助手，只有目标工程实际提供时才使用；没有就采用真实可用的查询、构建和文件工具，不运行缺失脚本。

## 更新与反馈

插件用户从原安装入口刷新/更新；手动用户重新下载并替换选定版本的整套技能。维护时从公共源码同步两版后一起发布，保留 Basic/Image 的资源差异。

发行前仍需游戏验收。上传工坊、更改游戏启用列表或启动游戏需要相应任务授权，不由安装技能自动执行。欢迎通过 Issues 提交问题，附客户端、游戏/上游版本、相关需求及必要的脱敏日志片段。

## English quick start

RimWorld ModDev Skill is a workflow for agents that support Agent Skills. Version **1.1.0** covers planning, Def/XML and C# work, upstream integration, debugging, assets, and release preparation.

Choose **Basic** for supplied or reused assets, or **Image** for a workflow that includes image generation. Enable one variant only. Image generation requires an actual tool or a configured, supported provider; the skill does not supply the service.

For manual setup, copy all five folders from `basic/skills/` or `image/skills/` into your mod project's `.agents/skills/`, keeping their `references/` folders. Cursor plugin users can install one variant through a supported marketplace/repository import. The manifests in this repository use Cursor's format.

Start with `rimworld-help` or `rimworld-setup`. For development, provide your game version, project/game paths, intended player behavior, constraints, and any selected upstream mods. Choose user-controlled values, agent-decided values, or a mixed mode. The agent establishes the actual content type, verifies templates/defaults and interfaces, records a concrete plan, and obtains confirmation before implementation unless an applicable prior approval or explicit delegation already exists.

Project records support incremental additions and resuming work. Evidence is reused only while its source and conditions remain valid. The package contains instructions and reference pages, not game code, development tools, local databases, or credentials. Static checks and compilation do not replace in-game acceptance.
