# RimWorld Mod 制作技能

这是一套给 Cursor 用的 Agent Skill，用来协助制作 RimWorld mod。仓库里有两个插件，内容来自同一套技能，差别只在贴图怎么来。

仓库地址：<https://github.com/pxy6666/Rimworld-ModDev-skill>

这不是 RimWorld mod 本体，也不包含游戏文件、编译工具、本机路径或密钥。技能只告诉代理怎么做 mod；真正的工程、Def 和代码仍在你自己的项目里。

## 选哪一版

两个插件里的五个技能名字相同。Cursor 里只安装其中一个。两个都装时，同名技能会叠在一起，代理无法稳定选用正确版本。

| 插件 | 目录 | 什么时候用 |
| --- | --- | --- |
| `rimworld-moddev-basic` | `basic/` | 贴图已经有了，或由你自己、外部提供。不接入平台生图。 |
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

团队计划也可以把这个仓库加为团队 marketplace，再由成员自行安装其中一个插件。

提交到 Cursor 官方插件市场是另一步，要到 [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish) 送审。本仓库推上 GitHub 之后，用上面的导入方式即可安装，不依赖官方市场上架。

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

- 技能假设目标工程自己有 packageId、Def 前缀和构建配置。不要把示例工程的身份套到新 mod 上。
- 本机游戏路径、工具路径放在使用方工程的本地配置里，不要写进这个仓库。
- 发行技能默认只做本地发行包。上传创意工坊需要你另行明确授权。
- 改技能正文不会改你已经打开的那个 mod 工程。装好之后，在 mod 工程里新开对话才会用到这些技能。

## 更新

使用者在 Cursor 里更新已安装的插件，或重新从本仓库导入。

作者改的是本地技能源，而不是直接改 GitHub 上的这两份副本。源改完并同步出 Basic、Image 后，再覆盖本仓库对应的 `basic/skills`、`image/skills` 并推送。两版要一起更新，避免公开副本和源不一致。
