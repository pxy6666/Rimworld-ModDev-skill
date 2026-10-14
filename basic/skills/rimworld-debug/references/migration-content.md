# 迁移内容与实际加载根

所有迁移都先核对此页，尤其是“玩法不变，只适配 DLL”。不要求所有 mod 必须有 Def，但原功能需要的 XML、补丁、语言和资源不能在新版本丢失。证据规则直接核对本机1.7.4977 rev1248的加载方法；其它构建变化时局部查证。

## 1. 迁移前保存内容基线

恢复原工程，列出1.6实际选择的内容根，以及各根下的 Def/模板、Patches、Languages、Textures、Sounds、Assemblies 和打包内容。保存代表性defName、逻辑路径、文件数量/哈希、提供方和条件；数量只帮助发现遗漏，不证明行为。将用户要求保留的功能关联到这些内容与消费者。

在已有项目记录保存 `角色/关键身份 → 原来源 → 1.7目标来源 → 复制/共享/调整/删除理由 → 加载与发行证据`。先保存冻结基线，再移动文件，避免用迁移后已改变的1.6视图冒充原始内容。原型也要明确内容缺项，不能把壳子称为迁移完成。

## 2. 为1.7落实内容，而非只创建目录

按真实工程选一条路线并实施：

- **版本实体副本**：保留1.6，将必要且兼容的Defs/Patches/Languages等复制到1.7；修订差异逐项处理，公共Textures/Sounds可继续在根目录。保持原身份和键，不复制旧Assemblies覆盖新DLL。
- **实体共享目录**：将已确认可共享的内容放入Common，分别为1.6/1.7显式选择Common及各版本目录；逐版核对旧功能与文件优先级，不重构所有现有布局。
- **沿用现有共享根**：已有根/Common内容无需搬动，但必须证明被目标分支选中。复用整个1.6根时它可能同时提供旧DLL，逐项核对实际程序集候选；不要以同名遮蔽作为所有DLL自动隔离的保证。

开发期内部链接可以复用内容；它不是可移植发行文件。禁止未经检查就把junction复制到另一台机器或ZIP。发行时在新的干净目录按已确认来源生成实体文件并复查，或采用实体Common布局；解析链接边界/循环，不能盲目遍历外部目标。

## 3. LoadFolders 指向内容根

游戏把每个选中的目录视为内容根，再拼接角色目录。`1.6/Defs`会查`1.6/Defs/Defs`；`1.7`才会查`1.7/Defs`。目录名字不是判定依据，重点是其下实际拥有正确角色目录。

显式分支选中后不会自动补入根或Common。示例仅适合采用实体Common的工程：

```xml
<loadFolders>
  <v1.6><li>/</li><li>Common</li><li>1.6</li></v1.6>
  <v1.7><li>/</li><li>Common</li><li>1.7</li></v1.7>
</loadFolders>
```

本机1.7按后列根优先，以完整逻辑相对路径遮蔽同路径文件；不同相对路径的DLL仍可能同时被读取。逐版列候选/胜出文件及Assembly身份，不只比较大小或文件名。

目录条件使用已核实的IfModActive、IfModActiveAll、IfModNotActive；实际组合未知时保留候选，不称已加载。不要把Def节点的MayRequire照搬成目录条件。没有明确分支、空分支或版本回退时核对实际选择，不能自行假定自动加载所有版本。

## 4. 对照检查与交付证据

技能附带只读 [content_load.py](../scripts/content_load.py)，用实际Python执行：

```text
python <当前rimworld-debug目录>/scripts/content_load.py check --root <mod根> --target 1.6 --out <mod根>/.local/migration-content-before.json
python <当前rimworld-debug目录>/scripts/content_load.py check --root <mod根> --target 1.7 --baseline-file <mod根>/.local/migration-content-before.json
```

若原内容完整保留在旧目录，也可用`--baseline-target 1.6`比较当前磁盘两版；它不代替冻结基线。工具输出限量文件，可保存完整本地记录；无Python采用同样清单人工/本地查询。脚本不执行补丁、条件组合或ContentPacks解包，也不证明Class/CrossRef/资源或游戏行为成立。

缺失必保留的定义/角色、选错根、丢掉补丁/语言或重复程序集要回制作修复；更名、替换和用户接受删除应在保留清单中解释并另验功能，不静默消除差集。纯C#系统mod按原入口/配置验收，不强造Def。

发行从最终干净包或独立解压目录再逐版核对内容根、关键Def、补丁、语言/资源及程序集，不用工作区可读的链接替ZIP背书。实际游戏确认代表性定义存在、获取与触发、原补丁效果/预期消费者；白名单/注册计数为0、Failed to find或空引用要追加载链。只改About、只生成DLL、只无自身报错、只进菜单均不足以证明内容迁移完成。
