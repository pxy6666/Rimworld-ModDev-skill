# C# 行为与状态

- 首先复用 API 或官方扩展点；选择 ThingComp、Verb、Hediff、JobDriver、组件等由职责决定，允许必要组合。
- 若功能由 Def 配置，定义 XML 配置面与读取者，再实现逻辑；CompProperties 设置 compClass，XML 指向配置类型。系统/显示功能也可由 Mod 启动与事件挂钩，使用 ModSettings 或合适配置方式，不为 C# 强造 Def。
- public 不等于稳定 API，检查类型可访问性、构造、生命周期、virtual/abstract 与约束。protected 覆写在合法派生类中完成。
- 编译引用实际游戏的 Managed 和已选上游；CLI runtime 与 mod 目标运行环境不同。沿用工程语言/目标，引用 DLL 不自动复制进发行包。
- 保存可变状态时明确 Scribe 键、默认值和读档重建；避免无必要更改类型名、defName、存档键。
- 高频 tick、扫描、事件回调和缓存按影响检查，避免无理由每 tick 分配/全图扫描。
- Harmony 根据执行时机用 Prefix/Postfix；不限制一项功能只能补一个方法。记录签名、条件、作用范围与修复后测试。Transpiler 说明更局部方式不足的原因。
- 编译通过后验证实际入口、适用的 XML 连接与行为；系统/显示功能另读 runtime.md。反编译 DLL 不等于已应用全部 Harmony 的运行代码。
