# RimWorld ModDev Skill

给 Cursor、Codex 等支持 Agent Skills 的代理使用的 RimWorld mod 开发流程。它帮助代理把玩家需求转换为可查证的 Def、XML、C# 和资源实现，也支持基于其他 mod 的调用、衍生与兼容补丁。

核心顺序是：**先确认用途与真实类型，再查模板和默认值；真正未定的玩法数值与资源才交给玩家或 CLI 决定。**

当前版本为 **2.1.0**。统一插件支持按 1.6 / 1.7 分流制作、排错和迁移，并按任务调用资源与发行流程。发行可交给工坊发布技能，按已验收的发行目录上传；每次发布都提交完整页面（描述、按 About.xml 生成的前置段、必需项目与 DLC 依赖、语言槽），超 1MB 的主图/截图自动压缩同一张图。技能内容包含 AI 辅助编写；静态检查、编译、游戏内验证和上传结果分别记录。

## 统一安装；按任务调用

现在只安装一个 `rimworld-moddev` 插件包，不再选择插件变体。统一包包含 13 个入口；`rimworld-art` 负责视觉资源，`rimworld-sound` 负责音效设计、制作、循环与声音验收。非美术/音频工作流不要求对应生成工具；需要时才使用实际可用的工具或用户提供的素材。

## 按版本选择入口

| 技能 | 什么时候用 |
| --- | --- |
| `rimworld-16-mod` / `rimworld-16-debug` | 明确面向 1.6 的制作或排错 |
| `rimworld-17-mod` / `rimworld-17-debug` | 明确面向 1.7 的制作或排错 |
| `rimworld-17-migrate` | 为已有 1.6 mod 在原工程增加 1.7 支持 |
| `rimworld-help` | 第一次使用、目标尚不明确，或不知道下一步 |
| `rimworld-setup` | 检查游戏路径、编译环境、检索/MCP 和必要工具能力 |
| `rimworld-mod` / `rimworld-debug` | 版本未定、双版本或继续使用旧名称时的路由入口 |
| `rimworld-release` | 核对成果、依赖与资源来源，生成本地发行目录、清单和收据 |
| `rimworld-publish` | 用户授权后将经核验的发行目录连同完整工坊页面（描述、必需项目与 DLC 依赖）上传到 Steam；可用同一记录续传 |
| `rimworld-art` | 普通美术、批量资源、Apparel 身体基准合成、渲染对位与视觉验收 |
| `rimworld-sound` | 音效设计、材质与尺度、制作/剪辑、动画同步、循环、响度与 SoundDef 契约 |

## 安装

### Cursor

本仓库保留 `.cursor-plugin/marketplace.json` 这一统一 Cursor 格式插件清单。客户端支持相应仓库/市场导入时，填入本仓库地址并安装 `rimworld-moddev`；具体入口以客户端文档为准，也可用下面的手动方式。[Cursor 插件文档](https://cursor.com/docs/plugins)

安装后可在 Agent 对话输入 `/rimworld-help` 或 `/rimworld-mod`，也可描述目标让代理匹配技能。[Cursor 技能文档](https://cursor.com/docs/skills)

### Codex、Claude Code、ZCode 与 Antigravity

- Codex：用 `codex plugin marketplace add pxy6666/Rimworld-ModDev-skill` 添加市场，再用 `codex plugin add rimworld-moddev@rimworld-moddev-skill` 安装。
- GitHub Copilot CLI：用 `copilot plugin marketplace add pxy6666/Rimworld-ModDev-skill` 添加市场，再用 `copilot plugin install rimworld-moddev@rimworld-moddev-skill` 安装。
- Claude Code：用 `/plugin marketplace add pxy6666/Rimworld-ModDev-skill` 添加市场，再用 `/plugin install rimworld-moddev@rimworld-moddev-skill` 安装。
- ZCode：在设置的插件市场中添加本 GitHub 仓库并安装 `rimworld-moddev`。
- Antigravity / Cursor-style local install：克隆仓库后，仓库根目录 `.` 就是本地插件根。Antigravity 可运行 `agy plugin validate .`、`agy plugin install .`，再用 `agy plugin list --json` 检查。Cursor-style 客户端请选择或导入仓库根目录。

### Codex / Cursor 手动安装

克隆或下载本仓库，把根目录 `skills/` 中**所有技能文件夹和 catalog.json 整体复制**到目标 mod 工程的 `.agents/skills/`：

```text
YourMod/
└── .agents/skills/
    ├── catalog.json
    ├── rimworld-16-mod/
    ├── rimworld-16-debug/
    ├── rimworld-17-mod/
    ├── rimworld-17-debug/
    ├── rimworld-17-migrate/
    ├── rimworld-art/
    ├── rimworld-sound/
    ├── rimworld-help/
    ├── rimworld-setup/
    ├── rimworld-mod/
    ├── rimworld-debug/
    ├── rimworld-release/
    └── rimworld-publish/
```

保留各技能中的 `references/`、`scripts/` 和 `data/`；不要只复制 SKILL.md 或把插件父目录一起放进去。已有同名技能先确认来源，不直接覆盖自己的修改。

本说明采用工程级 `.agents/skills/` 安装。会话中可直接要求“请使用 rimworld-help”，或指定对应版本技能；更新未显示时按客户端方式重新发现或开启新会话。其它安装方式以客户端文档为准。[OpenAI 技能文档](https://learn.chatgpt.com/docs/build-skills)

Cursor 也支持项目级 `.agents/skills/` 与 `.cursor/skills/`。两客户端在同一工程使用时可共享前者。单纯打开下载后的本仓库，不等于把技能安装进你的 mod 工程。[Cursor 技能目录](https://cursor.com/docs/skills)

手动复制是插件市场之外的备选方式。其它平台需支持相应技能加载，并具有工程文件访问与执行能力。

### 2.0.0 一次性迁移

从旧版升级时只需迁移一次：

1. 移除或禁用 `rimworld-moddev-basic` 或 `rimworld-moddev-image`；
2. 安装统一插件 `rimworld-moddev`；
3. 继续使用已有的制作、排错、迁移、发行和发布入口；
4. 图像任务交给 `rimworld-help` 路由到 `rimworld-art`，或直接调用 `rimworld-art`。
5. 音效任务交给 `rimworld-help` 路由到 `rimworld-sound`，或直接调用 `rimworld-sound`。

旧版两个插件不应与 2.0.0 统一插件同时启用。迁移不会改变已有工程的入口名称；只需按新的统一安装路径更新技能文件。

## 第一次使用

在实际 mod 工程中开始会话。提供已有项目位置、RimWorld 版本、游戏安装路径及有关 DLC；新工程也可以让代理先整理身份和结构。需要参考上游时提供其名称、路径或仓库，以及你想调用、衍生还是修正什么。

不知道环境是否准备好，可先说：

```text
请使用 rimworld-help。我要为 RimWorld 1.6 制作一个独立 mod。
先检查当前工程与所需环境，说明缺什么，再带我整理需求和计划。
```

明确制作目标时可以这样开始：

```text
请使用 rimworld-16-mod，制作一把可以直接远程投掷的吸血飞刀，目标1.6。
命中造成伤害后为使用者恢复生命，贴图复用原版。
先确认实际攻击类型与实现路径，再给我计划；不要立即制作。
伤害由我选择，其余未定数值参考原版决定，使用混合模式。
```

无需自己填写内部类名、全部 XML 或完整美术规格。代理负责技术查证；玩法取舍、必要资源来源和未定数值按你选的模式解决。

### 迁移与重做怎样选择

迁移时，先选择 **A 基本兼容**（保留约定功能、修复阻断和失效）或 **B 改进实现**（按选定目标评估新接口和必要重做）。未说明时代理会给选项，并澄清必须保留的功能、1.6支持、旧档与有关依赖，不自行默认。

需要重做界面/逻辑时，还要确认本次验收到哪里：

| 交付 | 验收边界 |
| --- | --- |
| 原型/技术交付 | 源码/配置及适用静态、编译检查；游戏未测明确列未验证 |
| 目标功能可用 | 实际操作触发预期结果，检查首次/重复及相关生命周期 |
| 可发行交付 | 功能可用，加选定版本/组合、资源和发行包检查；不自动上传 |

迁移程度与验收范围分别记录。局部重做不自动升级为整包改进；编译通过不能当作已可玩。代理会确认必测操作、预期、可接受保留项和测试分工，沿用已有选择，不重复问已决定的问题。

```text
请使用 rimworld-17-migrate，为这个1.6 mod增加1.7支持。
先让我选择迁移程度并梳理必须保留的功能。
如果需要重做设置界面，先确认验收范围和游戏测试分工，再给具体计划。
```

## 制作过程

1. 分解需求，判断内容的真实用途、类型、触发与执行链，初步判断是否需要 C#。
2. 对关键不确定方向给玩家选项，分析原版或上游 mod 提供的接口。
3. 复用有效证据，优先 MCP 小查询；必要时核对 XML、源码/DLL 或运行时 Def，形成配置契约与记录。
4. 展示经过技术自检的具体计划，确认计划与制作模式后进入制作；已有明确同意或自主规划实施委托可沿用。
5. 每个功能块核对类型/契约、补真正缺项、准备必要资源、制作并复查。
6. 检查整体获取、触发、组合与相关存档/视觉，准确报告通过、失败或未验证项。

独立的取证、已确认功能或审查任务可交给工具支持且获授权的子 agent；先固定依赖与文件归属，公共配置、合并和最终验收统一协调。没有子 agent 能力时按同一边界串行执行。

制作模式只处理真正未定项：

| 模式 | 谁决定 |
| --- | --- |
| 用户控制 | 代理提出有依据的候选与影响，玩家选择 |
| CLI 决定 | 在授权范围内参照同用途、匹配版本的原版或已选上游，并记录理由 |
| 混合 | 玩家锁定关键项，其余明确委托代理 |

已给定的合法 `0`/`false` 不算缺项；已满足目标的继承/默认不用重复填。字段常见不等于必填，少见不等于无效。“数值你定”也不自动代替整个计划确认。

### 迁移必须带上原内容

迁移先冻结旧版内容基线，再为1.7落实原有Def、补丁、语言与资源的实体副本或有效共享；只改About和编译DLL不算内容迁移完成。已有共享根无需机械搬动，但必须证明目标版本实际选择了它。

LoadFolders写内容根，如`1.7`，游戏会在其下找`Defs`等目录；写`1.6/Defs`会找`1.6/Defs/Defs`。显式分支不自动补根/Common。开发期链接不等于可移植发行文件，最终包需实体内容及逐版核对。

技能附带`rimworld-debug/scripts/content_load.py`，可在项目中保存旧版审计并对照新版本：

```text
python <当前rimworld-debug目录>/scripts/content_load.py check --root <mod根> --target 1.6 --out <mod根>/.local/content-before.json
python <当前rimworld-debug目录>/scripts/content_load.py check --root <mod根> --target 1.7 --baseline-file <mod根>/.local/content-before.json
```

它检查磁盘内容根、角色文件、命名Def差集和链接风险；条件组合、Assets.zip/ContentPacks、XML补丁执行与游戏行为分别留未验证，不能把静态通过当成已可玩。纯系统mod可以无Def，检查保留的是原功能所需内容。

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

普通图标、物件、建筑、UI 或单张贴图按普通美术流程处理；批量换款、多方向或需要地图图和菜单图标配套时，进入 [GFX 批量流程](skills/rimworld-art/references/gfx-batch.md)。Apparel、穿戴图或身体覆盖层必须先制作身体加服装的合成基准，再检查身体锚点和遮挡。坐标、render layer 和 shader 是三个独立检查，不能用其中一个检查代替另外两个。验收还要分别记录 source、文件、绑定/同步和 game 状态；没有实际工具输出以及后续绑定证据，不能宣称生成文件成功或视觉完成。

声音任务由 [rimworld-sound](skills/rimworld-sound/SKILL.md) 处理：先确认事件、材质、尺度和阶段时长，再制作试听样稿；循环必须验证首尾无缝，动画同步不能用变调伪造任意持续时间；文件响度、SoundDef 音量和游戏内听感分别检查。没有真实音频工具或实际试听产物时只停在 brief/缺口，不冒充音效完成。

按任务使用 [RimSage](https://github.com/realloon/RimSage)、[RimSearcher](https://github.com/kearril/RimSearcher)、[DecompilerServer](https://github.com/pardeike/DecompilerServer) 或已有检索工具，不要求同时安装全部能力。原始 XML、源码/DLL 和运行时 Def 各回答不同问题；MCP 不可用或版本不匹配时记录回退原因及剩余缺口。

美术批量生成前先审批代表性样例；样例通过后，再继续批量生成和其余风格。

游戏路径与相关程序集由使用方提供；C# 任务才准备适合目标游戏/上游的构建环境。贴图、声音和文本只请求本功能真正需要的部分，允许经确认的原版/上游运行时资源引用。图像来源偏好可记录在项目中，实际能否生成还要检查当前工具。

需要查当前安装时，按 [本地批量查证](skills/rimworld-mod/references/local-lookup.md) 查询 Def、父模板、类型、成员和静态引用。XML 查询只需 Python；首次构建 DLL 索引才需可用 .NET SDK，需要方法体时才按构建缓存反编译结果。缓存保存在本机。精选 `catalog.py` 仍可用于已记录的构建基线，迁移方向由 `compatibility.py` 查询。查不到不等于接口删除，静态资料不代替游戏实测。

此仓库分发技能、查询脚本、精选资料和发行打包器。提到的工程 `tools/preflight.ps1`、`tools/mod.ps1`、统计查询或资源导入助手，只有目标工程实际提供时才使用。

## 发行与 Steam 工坊

先用 [rimworld-release](skills/rimworld-release/SKILL.md) 核对游戏验收记录并打包。项目没有配套打包器时，从本仓库完整 checkout，以 Python 3.11+ 运行 `python <checkout>/tools/mod_cli.py package --root <Mod工程根> --target 1.7`，目标为 1.6 时替换参数。它会在工程下生成发行目录、文件哈希和发行收据。

使用 [rimworld-publish](skills/rimworld-publish/SKILL.md) 离线制定计划，核对具体发行目录及其验收记录和目标物品。每次发布都是完整发布：描述、按 About.xml（含按版本声明的依赖）生成的前置段、必需项目与 DLC 依赖、其他语言槽和变更说明都是必做项，缺项时计划直接拒绝；新建后把物品 ID 写回工程并重新打包再提交一次。可见性和截图由用户决定。主图或截图超过 1MB 时自动压缩同一张图（主图 PNG、截图 JPEG，需 Pillow）。确认计划并授权后，使用已登录的 Windows Steam 桌面客户端上传。保留本地 journal 以续传；结果未知时先查证再继续。[上传与恢复](skills/rimworld-publish/references/upload.md)

## 更新与反馈

插件用户从原安装入口刷新/更新；手动用户重新下载并替换统一插件的整套技能。维护时从公共源码同步统一包后一起发布。

发行前仍需游戏验收。上传工坊、更改游戏启用列表或启动游戏需要相应任务授权，不由安装技能自动执行。欢迎通过 Issues 提交问题，附客户端、游戏/上游版本、相关需求及必要的脱敏日志片段。

## English quick start

RimWorld ModDev Skill covers mod development, debugging, migration, art, sound and release for RimWorld 1.6 and 1.7. Version **2.1.0** provides 13 task-routed entries, including `rimworld-art` and `rimworld-sound`.

Install one `rimworld-moddev` plugin and call the entry that matches the task. Non-art workflows do not require image generation. For art, use an actually available image tool or user-provided assets; the skill does not supply that service.

For GitHub Copilot CLI, register the marketplace with `copilot plugin marketplace add pxy6666/Rimworld-ModDev-skill`, then install `rimworld-moddev@rimworld-moddev-skill` with `copilot plugin install rimworld-moddev@rimworld-moddev-skill`.

For manual setup, copy all skill folders and `catalog.json` from the repository-root `skills/` directory into your mod project's `.agents/skills/`, keeping references, scripts and data. The repository root `.` is the local plugin root. For Antigravity, run `agy plugin validate .`, `agy plugin install .`, and `agy plugin list --json`. For Cursor-style clients, select or import the repository root, or use the unified marketplace commands above.

Start with `rimworld-help` or `rimworld-setup`. For development, provide your game version, project/game paths, intended player behavior, constraints, and any selected upstream mods. Choose user-controlled values, agent-decided values, or a mixed mode. The agent establishes the actual content type, verifies templates/defaults and interfaces, records a concrete plan, and obtains confirmation before implementation unless an applicable prior approval or explicit delegation already exists.

For art, first approve a representative sample before batch generation. Worn graphics require a body-plus-apparel composite baseline. Check coordinates, render layer and shader separately, then record source-to-game states for files, binding, synchronization and in-game evidence. Generated-file output alone is not success without later binding evidence.

For sound, approve a representative audible sample before producing variants. Record the event, material, scale, timing and loop behavior; check file loudness separately from SoundDef volume, and validate animation synchronization, repeated playback and in-game acceptance.

### 2.0.0 one-time migration

Remove or disable `rimworld-moddev-basic` or `rimworld-moddev-image`, install `rimworld-moddev`, keep using the existing mod/debug/migration/release/publish entries, and let `rimworld-help` route image work to `rimworld-art`.

### Working with the skills

For migration, choose compatibility-first or improved implementation; if unspecified, the agent asks. For a rewrite, agree on technical delivery, usable target functionality, or release readiness, including relevant test cases and who supplies game-test evidence. These choices are independent; compilation is not gameplay acceptance. Independent work can be delegated to available, authorized subagents.

Project records support incremental additions and resuming work. Evidence is reused only while its source and conditions remain valid. The repository includes selected build catalogs, query scripts and a release packager.

For Workshop publishing, prepare a checked release directory with `rimworld-release`. Use `rimworld-publish` to plan and authorize an upload of that exact directory. Every publish is complete: the description with an About.xml-derived requirements section (DLC tags, Workshop links), Required Items and DLC dependencies, other language slots and, on updates, a change note are mandatory, and a plan missing any of them is rejected. After a first upload the item ID is written back to the project and the repackaged content is submitted once more. Visibility and screenshots are the user's decisions. Oversized previews and screenshots are re-encoded under the 1MB limit without substituting different art. Upload uses the Windows Steam desktop session. Keep the journal to resume a failed attempt, and verify ambiguous outcomes before retrying. [Upload and recovery](skills/rimworld-publish/references/upload.md)
