# RimWorld 根级公共技能与平台适配目录设计

## 状态

整体结构已在对话中批准；本文待用户审阅，不包含实施变更。

## 背景

当前仓库已经把 Basic/Image 合并为 `rimworld-moddev/`，但插件结构仍有第二层冗余：

- 仓库根目录保留市场清单。
- `rimworld-moddev/` 内同时保存公共 `skills/` 和六个平台插件清单。
- Claude、Cursor、Agents 市场索引仍从根目录指向 `./rimworld-moddev`。
- 根目录和插件子目录之间形成了两层“仓库/发行包”边界，但实际只存在一个插件。

`obra/superpowers` 的结构显示了更合适的模型：仓库本身就是唯一插件根目录，公共技能只有一份，各 Agent 只在自己的隐藏目录保存平台适配元数据。

## 目标

- 仓库根目录成为唯一 `rimworld-moddev` 插件根。
- 公共技能仅存在于根级 `skills/`。
- 每个 Agent/客户端只在自己的适配目录保存 manifest、marketplace 和必要 hooks。
- 所有市场条目都指向仓库根 `./`，不再指向 `./rimworld-moddev`。
- 保留现有 12 个技能、脚本、数据、测试和五个平台安装能力。
- 简化 README、工具定位和相对路径。

## 非目标

- 不为各 Agent 复制技能内容。
- 不引入符号链接作为主要分发机制。
- 不改变技能行为、RimWorld 版本支持或发行逻辑。
- 不同时维护 `skills/` 和 `rimworld-moddev/skills/`。
- 不删除某平台已有的必要 marketplace 元数据。

## 方案比较

### 方案 A：根级公共源码 + 平台适配目录

仓库根是插件本体；`skills/` 是唯一技能源码；各 Agent 使用独立隐藏目录。

- 优点：与 Superpowers 一致，无重复源码，市场路径和手动安装路径清晰。
- 缺点：一次性移动大部分文件并更新路径。
- 结论：采用。

### 方案 B：`plugins/<agent>/` 分目录

每个平台拥有独立插件目录，各目录引用或复制公共技能。

- 优点：肉眼上“按 Agent 分组”明显。
- 缺点：多数客户端期望根目录或平台约定的隐藏目录；还会引入重复、引用或构建同步问题。
- 结论：不采用。

### 方案 C：保留内部目录并生成根适配

把 `rimworld-moddev/` 当源码，构建时生成平台入口。

- 优点：源码不动，理论上可保留旧路径。
- 缺点：同时维护源码和生成产物；本项目仍是单插件，构建层不提供足够收益。
- 结论：不采用。

## 目标目录

```text
repo/
├── .agents/plugins/marketplace.json
├── .antigravity-plugin/plugin.json
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── .codex-plugin/plugin.json
├── .cursor-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── .zcode-plugin/plugin.json
├── skills/
│   ├── catalog.json
│   ├── rimworld-16-mod/
│   ├── rimworld-16-debug/
│   ├── rimworld-17-mod/
│   ├── rimworld-17-debug/
│   ├── rimworld-17-migrate/
│   ├── rimworld-help/
│   ├── rimworld-setup/
│   ├── rimworld-mod/
│   ├── rimworld-debug/
│   ├── rimworld-art/
│   ├── rimworld-release/
│   └── rimworld-publish/
├── tools/
│   └── mod_cli.py
├── tests/
├── docs/
├── marketplace.json
└── README.md
```

`rimworld-moddev/` 整个目录在迁移后删除。

## 职责边界

### 公共技能根

`skills/` 是唯一内容源：

- 所有技能的 `SKILL.md`、`references/`、`data/`、`scripts/`。
- `catalog.json` 作为唯一技能索引。
- 不保存 Agent 特定配置、marketplace 清单或插件元数据。

### Agent 适配目录

每个平台目录只描述如何让该 Agent 加载同一份技能：

- Codex：`.codex-plugin/plugin.json` 使用 `"skills": "./skills/"`。
- Cursor：`.cursor-plugin/plugin.json` 使用 `"skills": "./skills/"`，并保留必要 hooks 字段。
- Claude：`.claude-plugin/plugin.json` 与 marketplace 合并到同一目录；Claude 发现插件根和公共 `skills/`。
- Antigravity：`.antigravity-plugin/plugin.json` 保留该平台展示信息与推荐提示。
- ZCode：`.zcode-plugin/plugin.json` 保留该平台名称、作者和仓库元数据。
- Agents/GitHub Copilot：`.agents/plugins/marketplace.json` 指向仓库根。

根级各 Agent 目录之间不得复制 `rimworld-*` 技能。

### Marketplace 与插件清单

仓库级市场索引保留，但只指向当前仓库根：

- `.agents/plugins/marketplace.json`：source 对应 `./`。
- `.claude-plugin/marketplace.json`：source 对应 `./`。
- `.cursor-plugin/marketplace.json`：source 对应 `./`。
- `marketplace.json`：如仍为兼容入口，也只记录 `source: "./"`；它不创建第二个插件源码目录。

每个平台目录中的 `plugin.json` 必须共享相同插件名 `rimworld-moddev` 和版本。

## 路径迁移

### 移动

- `rimworld-moddev/skills/` → `skills/`
- `rimworld-moddev/.antigravity-plugin/` → `.antigravity-plugin/`
- `rimworld-moddev/.codex-plugin/` → `.codex-plugin/`
- `rimworld-moddev/.zcode-plugin/` → `.zcode-plugin/`
- `rimworld-moddev/.claude-plugin/plugin.json` → `.claude-plugin/plugin.json`
- `rimworld-moddev/.cursor-plugin/plugin.json` → `.cursor-plugin/plugin.json`

Claude 与 Cursor 的根级 marketplace 文件保留；两类文件合并在同一平台目录，不复制到子插件目录。

### 删除

- `rimworld-moddev/`
- `rimworld-moddev/plugin.json`
- 所有指向 `./rimworld-moddev`、`rimworld-moddev/skills` 或从 nested plugin root 回跳公共源码的旧路径。

### 工具

`tools/mod_cli.py` 直接将仓库根 `skills/` 作为 bundled skills 根。由于仓库本身就是插件根，不保留 `rimworld-moddev/skills` fallback。

如果工具无法找到 `skills/catalog.json`，应明确报错，而不是悄悄回退到不存在的旧目录。

## 安装与文档

README 统一为：

- 市场安装：安装 `rimworld-moddev@rimworld-moddev-skill`。
- 本地 Antigravity/Cursor style 安装：插件根为 `.`，不是 `./rimworld-moddev`。
- 手动技能安装：复制根级 `skills/`。
- 所有内部文档链接指向 `skills/...`。

用户不需要知道平台适配目录；这些目录用于各 Agent 发现和安装同一个插件。运行时行为仍按 Agent 的现有 plugin/schema 约定执行。

## 兼容边界

迁移时一次性修改所有平台入口，避免一部分市场指向新根而另一部分仍指向已删除目录。

短期不保留 `rimworld-moddev/` 兼容壳。该目录只会重新引入“根目录与插件目录并存”的双层结构，并破坏“公共源码只有一份”的目标。已有用户的 2.0.0 迁移说明可保留，但下一次插件更新从根目录重新安装。

平台特定 schema 必须保留：

- 不把 Codex 的显式 `skills` 字段机械复制给不接受它的平台。
- 不删除 Cursor 的 hooks 字段。
- 不用通用 JSON 猜测 Antigravity/ZCode 字段。
- 市场清单继续使用各自原格式，仅改变 source 路径。

## 错误处理

- 如果平台 `plugin.json` 依赖安装包内部根，迁移时验证其相对路径可从仓库根解析。
- 如果 `skills/` 中相对链接使用 `rimworld-moddev/skills` 前缀，必须全部更新。
- 如果测试只验证目录名存在，增加内容与目录一致性测试，防止再次出现空壳或双份源码。
- 如果 `mod_cli` 找不到公共技能，返回明确的缺失目录错误；不返回不存在路径。

## 验证

实施完成至少验证：

1. 根级 `skills/` 包含 12 个目录，`catalog.json` 与目录完全一致。
2. `rimworld-moddev/` 不存在。
3. 六个平台 manifest 都在根级约定目录。
4. 每个 marketplace 的唯一插件 source 解析为仓库根。
5. Codex/Cursor manifest 的 skills 路径可解析到根 `skills/`。
6. `skills/` 下所有 Markdown 相对链接有效。
7. `tools/mod_cli.py` 能找到 `rimworld-debug` 与 `rimworld-mod` 的 shipped helper。
8. README 不再把 `rimworld-moddev/` 描述为安装根。
9. 原 12 个技能测试与 art/Apparel/render fixtures 全部通过。
10. JSON、`git diff --check`、CLI help 与最终文件边界检查通过。

## 完成定义

仓库根本身就是 `rimworld-moddev` 插件；公共技能只有根级 `skills/` 一份；每个平台只有自己的根级适配目录；所有市场与文档从根目录安装；工具、链接和测试全部指向统一根布局。
