# XML 与补丁

先按 [classification.md](classification.md) 确认用途、实际类型/配置 Class 与执行链，再按 [contracts.md](contracts.md) 核对模板、继承、合法默认和值来源。类型表和频率表只帮助查证，不是完整必填清单。实现时读取功能记录并保存变更/验证，见 [project-state.md](project-state.md)。

- 用实际同类 Def 核对字段。Name/Abstract 是模板，ParentName 指模板 Name；不要从运行时 defName 猜模板。
- 区分继承、覆写、列表追加与替换。子项可以覆写父级字段；先确认是否重复继承 comps/verbs。
- 补丁的 XPath 针对加载输入，需考虑此前补丁；继承后字段存在不证明输入目标存在。只改必要节点，应用后再验证最终值。
- 按 Def 类型检查 defName 重复，采用工程命名前缀；引用原版身份不重命名。
- Class、workerClass、compClass 等核对配置类型与实际基类；读取 DLL 不影响纯 XML 成果范围。
- 条件内容根据目标加载器核对 MayRequire、条件补丁和 LoadFolders；DLC 既可必要也可可选，依据主要功能决定。
- 静态检查未实现完整继承/补丁执行/ConfigErrors 时明确报告，游戏加载和行为单独验收。
