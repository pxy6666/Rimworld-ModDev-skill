# 地图与结构生成

在任务地点、新地标、预制结构或口袋地图需要制作或排错时读取。本页使用本机 Core、Odyssey 和 Anomaly 的 `1.7.5014 rev1195` XML 与同构建程序集作为静态参考。实际制作查目标构建、DLC 状态和已选上游。各案例列出的数值只用于定位原版。

## 选择生成层

| 需求 | 首先核对的生成入口 |
| --- | --- |
| 在世界地图上出现任务地点或地标 | `WorldObjectDef.mapGenerator`、`MapParent`、`SitePartDef`；地标可查目标世界格的 `TileMutatorDef` 和 worker。查星球层、地块、地图尺寸、访问方式、超时和补给返回路线。 |
| 先配置世界地点，再增加场景的局部内容 | 在目标地图生成器的实际步骤中找接入点。地点专有内容可用 `GenStepDef.linkWithSite` 接到 `SitePartDef`，步骤可以另命名。查看地点参数如何传进 `GenStep`。 |
| 实现整张地表、轨道或地下地图 | 选择匹配环境的 `MapGeneratorDef`，核对默认步骤和额外步骤来源。开局剧本可给起始世界格和生成器设定专用条件。地图内的 `MapPortal` 可延迟生成独立口袋地图并关联返回出口。 |
| 放一栋固定建筑、一组设施或一个地板图案 | `PrefabDef` 支持尺寸、相对坐标、矩形、地形、旋转、概率和嵌套。核对放置后的占地、材质、门洞和与地形的连接。根据具体场景也可复用 SketchGen。 |
| 由种子选布局、房间与陈设 | `StructureLayoutDef`、`LayoutRoomDef` 或实际 resolver，可将重要房间、房间权重、内容 worker、散布和外围残骸分别配置。BaseGen 也用于原版据点。 |

读取生成器的实际步骤清单和调用路径，确认生成时的读写关系。典型依赖是地形可用 → 目标结构占用 → 场景内容 → 必要的供电、出口或清理。核对是否还有生物群系、地点、世界格或 Mod 附加步骤。奖励物件、目标房或出口等必需内容需要明确的放置保证或失败出路。散布和碰运气适合可省略内容。

## 地图内容与任务交接

| 内容 | 制作与检查 |
| --- | --- |
| 地面、房间和通路 | 约定固定区域、房间权重、必有区域、最小格数以及碰撞时如何选择替代位置。检查玩家、守卫与目标各自的可达区。落点、撤离点、脚本目标分别核对。 |
| 物品、资源点与容器 | 分别记录数量、概率、总量上限、预算、来源和固定点或区域。选适用的 `ThingSetMaker`、预制体、房间 worker 或专用步骤。标出现场可拾取、清关后解锁和交付后结算三类来源，核对重进后的实际行为。 |
| Pawn 与守卫 | 记录固定角色或生成组、派系、点数、站位、休眠、激活和撤离。使用已验证的 `PawnGroupMaker`、`LordJob` 或自有行为接口。单独确认有名字或要跨章节继承的 Pawn 由谁持有。 |
| 炮塔、陷阱及其他设施 | 检查派系、供电或触发、射程或影响区、放置失败时的行为。核对设计预期是从进图即激活、由交互启用，还是完成某条件后解除。 |
| 任务目标与出口 | 按[交接记录](feature.md#任务与地图交接)记录实际生成和绑定。对重复 Def 用区域、角色、对象引用或可信标签区分实例。 |

明确撤离、回访和重新生成时是否保留地图及实例。地图卸载后，世界地点仍可能存在。地点摧毁、超时或任务终止时，按各自的触发清理。根据设计核对回访要继承或重刷的资源、敌人、开关和出口。跨图传送核对源图、目标图、实际出口和任一侧被移除后的处理。涉及任务推进和去重时查[任务状态](quest-state.md)。

需要骇入、销毁或带走对象时，核对生成后的实际目标绑定及[任务信号](quest-events.md)。目标可能在绑定前被处理时，绑定后根据实际状态决定是否补记，并合并重复通知。目标缺失、无法互动、出口不可用或地图提前关闭时，执行约定的替代位置、失败或重试。

有生成参数时，记录单位、有效范围、默认来源、权威配置和读取时机。

## 参考定位

- **Core 强盗营地。** `Data/Core/Defs/Sites/Parts/BanditCamp.xml` 通过 `linkWithSite` 接 `GenStep_Outpost`（400）和独立供电（401）。Outpost 用派系、威胁点数、物资价值和种子驱动 BaseGen 的据点与守军。`Data/Core/Defs/QuestScriptDefs/Script_BanditCamp.xml` 对照 `site.MapGenerated`、`site.Destroyed`、`site.AllEnemiesDefeated` 各自承担的推进和结算。
- **Odyssey 机械巢穴。** `Data/Odyssey/Defs/MapGeneration/MechhiveMapGenerator.xml` 用专用轨道生成器，主体步骤在 290，之后还有零件和杂物散布。`LayoutDefs/Layouts_Mechhive.xml` 定义重要的稳定器房间与房间池，`PrefabDefs/MechhivePrefabs.xml` 提供核心周边设施与炮塔坐标。地图生成后 `QuestPart_CerebrexCore` 查找实际对象、挂任务标签并保存引用。世界格主体与外围设定另可查 `TileMutators/TileMutators_AncientStructures.xml`。
- **Anomaly 地坑与迷宫。** `Data/Anomaly/Defs/MapGeneration/UndercaveMapGenerator.xml` 将洞穴、出口、实体和兴趣点分步生成。查 `MapPortal.GetOtherMap`、`CompDreadmeld.Notify_Killed` 与地表入口持有的坍塌状态了解跨图回传。迷宫在 `MapGeneration/LabyrinthMapGenerator.xml` 中用专用生成步骤（10），其房间布局见 `LayoutDefs/Layouts_Misc.xml`。虚空终局的 `MetalHellMapGenerator.xml` 还有中心目标和程序化地形一同生成的案例。

本机 Core 有 `Data/Core/Defs/PrefabDefs/CommonRoomPrefabs.xml`，Anomaly 迷宫也消费布局。依赖判断落实到目标构建实际采用的 Def、worker、内容提供方和运行前提。引用了 Odyssey 的地形、资产或设施时再据证据声明 DLC。

## 验收场景

复现记录写清目标构建和 DLC、实际进入方式、`MapGeneratorDef`、地图尺寸。适用时带上世界格与星球层、世界或场景种子、首次生成或重进的条件。种子来源与复现步骤一起记录。

| 检查 | 可复现的动作 |
| --- | --- |
| 地图生成与加载 | 通过真实入口进入，观察关键地形、占地、必有目标、物资、守卫和供电等实际生成结果。 |
| 玩家可达与实际触发 | 从实际落点到达目标及出口，执行关键操作，检查是否从预期实例发出信号或产生可观察结果。任务端的推进、奖励和清理结果单独交回集成验收。 |
| 生成变体与边界 | 对随机场景用能覆盖不同布局的种子，以及有意义的边界，如较小合法尺寸或地块受阻。核对主要目标和退出路径仍可用。对固定场景核对实际会使用的旋转和入口。 |
| 存读档、重进与跨图 | 选择受改动影响的交互前后节点，保存重载及往返，核对目标身份、出口绑定与地图物资。适用时分别覆盖普通撤离、地图卸载后回访以及地点销毁或关闭。 |
