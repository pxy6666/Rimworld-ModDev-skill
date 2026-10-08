# RimWorld Mod 制作技能

*本skill基本由AI制作，所以需要注意部分内容是否正确，如有建议或疑问谨请指出*

这是一套给 Cursor和Chatgpt 用的 Agent Skill，用来辅助制作 RimWorld mod。仓库里有两个插件，流程和内容相同，一个（IMAGE版）是把图片生成带进skill过程的，另一个就没有。

仓库地址：<https://github.com/pxy6666/Rimworld-ModDev-skill>

这不包含游戏文件、编译工具、本机路径或密钥。技能只告诉代理怎么做 mod，也需要明确游戏的路径（用于参考原版和dlcXML）或者在需要时向CLI提交需要参考或基于制作的mod；

目前skill会参考rimworld游戏本体和dlc文件和Harmony（lib mod），可能会用到：RimSage，RiMCP hybrid ，RimSearcher 和DecompilerServer

## 选哪一版

两个插件里的五个技能名字相同。Cursor 里只安装其中一个。两个都装时，同名技能会叠在一起，代理无法稳定选用正确版本。

| 插件 | 目录 | 什么时候用 |
| --- | --- | --- |
| `rimworld-moddev-basic` | `basic/` | 贴图已经有了，或由你自己、外部提供。不依赖CLI平台的其他模型或者调用方式生图。 |
| `rimworld-moddev-image` | `image/` | 需要从外观需求走到资源规格、平台生图、导入、视觉检查和引用绑定。 |

两版都包含六种制作范围，以及需求、计划、制作、复查。两版都会核对贴图是否绑上、看起来是否正确，并要求游戏内证据。Basic 不调用生图计划和导入。

## 五个技能

安装后，在 Agent 对话里输入 `/`，可以按名字叫出对应技能。描述匹配时，代理也会自己选用。

| 技能 | 作用 |
| --- | --- |
| `rimworld-help` | 第一次使用，或不确定下一步时。它读取当前状态，告诉你该用哪个技能。 |
| `rimworld-setup` | 检查并准备开发环境。适用于缺依赖、换电脑，或检索、MCP 连不上。 |
| `rimworld-mod` | 制作或修改 mod：Def、C#、界面、上游整合，以及完成后的验证。 |
| `rimworld-debug` | 诊断加载、运行、兼容、存档、性能和游戏版本迁移问题。 |
| `rimworld-release` | 准备发行包，核对版本、依赖、素材许可和验证记录。只有明确要求上传工坊时才执行发布。 |

Image 版的 `rimworld-mod` 额外带有 `references/image-pipeline.md`。Basic 版没有这个文件。

## 在 Cursor 里安装

1. 打开 Cursor 的 Customize。
2. 选择从 GitHub 仓库导入（From GitHub Repository）。
3. 填入 `https://github.com/pxy6666/Rimworld-ModDev-skill`。
4. 在列出的两个插件里只安装一个：Basic 或 Image。
5. 新开一个 Agent 对话。若列表里仍是旧技能，重新打开 Cursor 后再试。

这个仓库根目录有 `.cursor-plugin/marketplace.json`，Cursor 靠它识别两个插件。只把文件夹克隆到本地、用 Cursor 打开，技能不会自动生效，因为技能不在 `.agents/skills/` 或 `.cursor/skills/` 里。
也就是说需要自己手动安装一下或者直接交给CLI帮你安装。

## 目录

```text
.cursor-plugin/marketplace.json    两个插件的清单
basic/.cursor-plugin/plugin.json   Basic 插件说明
basic/skills/                      五个技能
image/.cursor-plugin/plugin.json   Image 插件说明
image/skills/                      五个技能，多出生图流程
```

每个技能是一个文件夹，入口是 `SKILL.md`。较长的说明在同级 `references/` 里，代理需要时才读取。

## 使用时要注意

- 技能假设目标工程自己有 packageId、Def 前缀和构建配置。不要把示例工程的身份套到新 mod 上，如果需要，请把情况向agent说清楚。
- 本机游戏路径、工具路径放在使用方工程的本地配置里，不要写进这个仓库。
- 发行技能默认只做本地发行包。上传创意工坊需要你另行明确授权或直接进行操作。
- 改技能正文不会改你已经打开的那个 mod 工程。装好之后，在 mod 工程里新开对话才会用到这些技能。

## 更新

使用者在 Cursor 里更新已安装的插件，或重新从本仓库导入。

作者改的是本地技能源，而不是直接改 GitHub 上的这两份副本。源改完并同步出 Basic、Image 后，再覆盖本仓库对应的 `basic/skills`、`image/skills` 并推送。两版要一起更新，避免公开副本和源不一致。


RimWorld Mod Development Skill

*This skill was mostly created by AI, so note that some content may be incorrect. If you have suggestions or questions, please point them out.*

This is an Agent Skill for Cursor and ChatGPT, used to assist with RimWorld mod development. The repository contains two plugins with the same workflow and content. One (the IMAGE version) brings image generation into the skill process; the other does not.

Repository URL: https://github.com/pxy6666/Rimworld-ModDev-skill

This does not include game files, build tools, local paths, or keys. The skill only tells the agent how to make a mod. You still need to specify the game path (for referencing vanilla and DLC XML), or, when needed, submit to the CLI the mod that needs to be referenced or used as a base.

Currently, the skill references RimWorld base game and DLC files and Harmony (lib mod), and may use: RimSage, RiMCP hybrid, RimSearcher, and DecompilerServer.

Which Version to Choose

The five skills in the two plugins have the same names. Install only one of them in Cursor. If both are installed, skills with the same names overlap, and the agent cannot reliably choose the correct version.

Plugin	Directory	When to use

rimworld-moddev-basic	basic/	Textures already exist, or are provided by you or externally. Does not rely on other models on a CLI platform or invocation methods to generate images.
rimworld-moddev-image	image/	Need to go from appearance requirements to asset specs, platform image generation, import, visual inspection, and reference binding.
Both versions include six modding scopes, plus requirements, planning, production, and review. Both versions check whether textures are bound, whether they look correct, and require in-game evidence. Basic does not invoke image-generation planning and import.

Five Skills

After installation, type / in the Agent chat to invoke the corresponding skill by name. The agent will also select them automatically when the description matches.

Skill	Purpose

rimworld-help	For first-time use, or when you are unsure of the next step. It reads the current state and tells you which skill to use.
rimworld-setup	Checks and prepares the development environment. Useful for missing dependencies, switching computers, or retrieval/MCP connection issues.
rimworld-mod	Creates or modifies mods: Def, C#, UI, upstream integration, and post-completion verification.
rimworld-debug	Diagnoses loading, runtime, compatibility, save, performance, and game version migration issues.
rimworld-release	Prepares release packages and verifies version, dependencies, asset licenses, and verification records. Only performs publishing when explicitly asked to upload to the Workshop.
The Image version's rimworld-mod additionally includes references/image-pipeline.md. The Basic version does not have this file.

Installing in Cursor
Open Cursor's Customize.

Choose import from GitHub Repository.

Enter https://github.com/pxy6666/Rimworld-ModDev-skill.

Install only one of the two listed plugins: Basic or Image.

Open a new Agent conversation. If the list still shows old skills, reopen Cursor and try again.

The repository root contains .cursor-plugin/marketplace.json, which Cursor uses to recognize the two plugins. If you only clone the folder locally and open it with Cursor, the skills will not take effect automatically, because the skills are not in .agents/skills/ or .cursor/skills/. In other words, you need to install them manually yourself or let the CLI install them for you.

Directory

.cursor-plugin/marketplace.json    Manifest for the two plugins
basic/.cursor-plugin/plugin.json   Basic plugin description
basic/skills/                      Five skills
image/.cursor-plugin/plugin.json   Image plugin description
image/skills/                      Five skills, with an extra image-generation workflow
Each skill is a folder, with SKILL.md as the entry point. Longer explanations are in the sibling references/ directory, which the agent reads only when needed.

Usage Notes

The skill assumes the target project has its own packageId, Def prefix, and build configuration. Do not apply the example project's identity to a new mod. If needed, explain the situation clearly to the agent.

Local game paths and tool paths should be placed in the local configuration of the consuming project, and must not be written into this repository.

The release skill only creates local release packages by default. Uploading to the Steam Workshop requires separate explicit authorization from you, or you must do it directly yourself.

Editing the skill text will not modify the mod project you already have open. After installation, these skills are only used when you start a new conversation in the mod project.

Updates

Users update the installed plugin in Cursor, or re-import from this repository.

The author modifies the local skill source, not these two copies on GitHub directly. After modifying the source and syncing out Basic and Image, overwrite the corresponding basic/skills and image/skills in this repository and push. Both versions must be updated together to avoid inconsistency between the public copies and the source.
