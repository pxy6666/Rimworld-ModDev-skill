# 目标与证据契约

先恢复目标 1.6、1.7 或双版本。用户目标优先于当前安装；双版本各建记录。资料画像在 `../data/profiles/`，最小数据契约为 [catalog-contract.json](../data/catalog-contract.json)。画像是已检查构建的事实，不代表其它修订版自动兼容。

## 记录与查询

当前技能附 [catalog.py](../scripts/catalog.py)，可用实际 Python 做限量查询；无 Python 时只读匹配条目，不把整表贴进上下文：

```text
python <当前rimworld-mod目录>/scripts/catalog.py profile --target 1.7
python <当前rimworld-mod目录>/scripts/catalog.py query --target 1.6 --type Verse.ThingDef --symbol comps
python <当前rimworld-mod目录>/scripts/catalog.py query --target 1.7 --purpose ui --limit 5
python <当前rimworld-mod目录>/scripts/catalog.py recipes --target 1.7 --purpose ui --limit 5
python <当前rimworld-mod目录>/scripts/catalog.py verify --target 1.7 --game-root <本机游戏根> --harmony-root <实际Harmony包根>
```

精选目录包含声明成员和私有事实，不等于合法扩展面；默认值、继承成员、泛型约束及行为语义未全量采集。`verify` 只核对文件身份，不能证明游戏实际加载了哪份库。两版画像各自链接覆盖范围；用法与原创样例见 [usage-examples.md](usage-examples.md)。

只有 PowerShell 时可在进程内解析 JSON，按 type/name 等筛选后只输出前几项；不要直接输出整份 Get-Content -Raw。缺少合适解析能力时采用小范围本地取证，不为查一项先装全部工具。

- 项目保存目标、画像 id、游戏构建、程序集身份/哈希、DLC/上游加载组合、工具索引来源、功能契约和未验证项。本机路径留在本地配置。
- 接口用画像、程序集哈希、完整类型和签名定位，区分重载/泛型/ref/out；显示名不作唯一键。用法/原创样例关联符号 id 和消费者，不抄反编译正文。
- 查不到分别处理：已证实缺失、未覆盖、解析失败、证据过期；歧义先消歧。只有有效完整覆盖或指定符号的直接取证才可断言不存在。
- 元数据/XML/源码/编译/加载/触发/生命周期/存档/视觉/测量分别记录，不从前者推出后者。修改源、配置、上游或游戏构建时只失效受影响证据。

制作先按用途/真实类型查契约与模板，展开有关接口；排错从异常/触发行为查诊断或兼容表；迁移先看实际依赖和风险。涉及补丁才查 Harmony，涉及资源才查资源页。有效检查点复用，避免全表读入上下文。

优先已接通且来源匹配的小 MCP/CLI 查询；在线/旧索引不能证明本机新版本。工具缺失或覆盖不足时局部查原始 XML/源码/DLL并记录回退原因。接口事实不保证调用时机、线程、资源所有权或序列化安全。

每个功能的验收记录：触发动作、预期、首次/重复及相关生命周期实际结果、通过/失败/未验证/用户接受保留项。核心未触发不能算通过；只选相关场景，库增加最小消费者，可选兼容核对有/无上游。
