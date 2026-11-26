# 首批用法与原创样例

按用途查询，不按 API 字母表从头读。[recipes.json](../data/recipes.json) 把用途、两版精确符号 id、条件、失败场景和独立验证状态关联；这些是精选起点，未覆盖所有配置/行为，原版/上游消费者仍需局部取证。

| 用途 | 实际连接与侧重 |
| --- | --- |
| 内容附加行为 | ThingDef.comps → 自有 CompProperties → compClass → ThingComp；XML 配置面以解析和消费者为据 |
| 设置 | Mod → ModSettings → ExposeData / Scribe_Values；默认值、键和读档恢复分开核对 |
| 新界面 | Window → DoWindowContents → 数据/输入/输出；核对创建、注册和关闭，不因 C# 多就强造 Def |
| 使用库或衍生内容 | 真实公开/可继承入口或上游 Def/Class → 自有消费者；依赖与可选加载分别记录 |
| 局部 Harmony | 精确目标 → 声明/绑定 → 原路径和补丁路径；调用库与修正目标分开 |
| 发射投射物 | 武器用途 → VerbProperties/Verb_LaunchProjectile → Projectile/伤害；名字“飞刀”不意味着近战 |

## Comp 连接骨架

下面是原创的最小声明骨架，不是完整内容 mod，也未经过本轮游戏测试。将 XML 节点挂在已查证能承载 comps 的目标上；是否需要该组件及 amount 的玩法意义由本功能决定。

```csharp
namespace Example {
    public sealed class CompProperties_Example : Verse.CompProperties {
        public float amount = 1f;
        public CompProperties_Example() { compClass = typeof(CompExample); }
    }
    public sealed class CompExample : Verse.ThingComp {
        public override void PostSpawnSetup(bool respawningAfterLoad) {
            base.PostSpawnSetup(respawningAfterLoad);
            // 按已确认需求实现；读档恢复不能重复注册副作用。
        }
    }
}
```

```xml
<li Class="Example.CompProperties_Example">
  <amount>1</amount>
</li>
```

这段 XML 是 comps 内节点，不能当独立 Def 文件。只配 Class 不实现读取行为仍不满足玩法；构造设置 compClass 与 XML Class 是不同职责。

## 序列化与补丁声明骨架

`Scribe_Values.Look(ref enabled, "enabled", true, false)` 示例显式提供四项参数，避免从未采集的参数默认值猜调用；变量、默认值和键应采用当前工程的已确认契约，迁移时勿把示例键覆盖旧键。

Harmony 可按本库真实 `Patch` 重载，传入实际 `MethodBase` 和 `HarmonyMethod`，不为样例选择一个未经证实的游戏目标。Prefix/Postfix 名称不是兼容保证：目标 owner、注入签名、执行时机、其它补丁和实际触发仍须验证。需要运行样例时先建立隔离的最小测试工程，编译与运行状态分别回填。
