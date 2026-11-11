# 常用机制：建筑与工作

按功能读对应段，先复用与目标构建及实际类型相符的证据。以下是 **1.7.5000 rev1275** 的本机原版静态查证：根目录 `Assembly-CSharp.dll`（SHA256 `d55aa8e47fa3c5463ca85b0eccd51f195b4bbcd04f56da3af21c2f6688a81254`）及下列 Core XML。未启动游戏；不推定 1.6、其他构建或上游改写后的行为。构建、文件或消费者变化时，只补查受影响的入口。

## 建筑同格与桌面装饰

- 同格要分别核对下蓝图、施工和成品生成。候选配置：`building/isEdifice=false` 避开两个主体建筑的冲突分支；顶层 `clearBuildingArea=false` 避开部分施工清场；`altitudeLayer=BuildingOnTop` 用于绘制分层。这三项不能保证桌面放置：还要检查双方的 `blocksAltitudes`、主体的 `building/canBuildNonEdificesUnder`、放置规则与放置工人。蓝图生成复制 `clearBuildingArea`；框架另外复制 `building/isEdifice`。
- 查 `RimWorld.GenConstruct.CanPlaceBlueprintOver`、`RimWorld.GenConstruct.BlocksConstruction`、`Verse.GenSpawn.SpawningWipes`、`RimWorld.ThingDefGenerator_Buildings.NewBlueprintDef_Thing` / `NewFrameDef_Thing`。原版参照：`Buildings_Furniture.xml → WallLamp` 展示非主体的上层附着物；其墙面约束不能照搬作桌面模板。实测先建桌再放、先放再建，以及拆除主体、旋转和读档。

## 设施连接与工作速度

- 设施端用 `RimWorld.CompProperties_Facility.statOffsets`，接收建筑端用 `RimWorld.CompProperties_AffectedByFacilities.linkableFacilities`。先核对类型白名单、距离/邻接、容量和启用状态。原版 `RimWorld.CompAffectedByFacilities.GetStatOffset(StatDef)` 累加当前活动设施的偏移；`RimWorld.StatWorker.GetValueUnfinalized` 读取目标 Thing 的组件偏移。连上建筑不会直接给使用者加 Pawn 属性。
- 普通配方工作量有两条属性路径：`Verse.AI.Toils_Recipe.DoRecipeWork` 从 Pawn 读取 `RecipeDef.workSpeedStat`，从 `RimWorld.Building_WorkTable` 读取并乘上 `RecipeDef.workTableSpeedStat`。`Verse.RecipeDef.ResolveReferences` 在未配置后者时设为 `WorkTableWorkSpeedFactor`。所以即使 `CookMealSimple` 从 Pawn 读取 `CookSpeed`，仍可从已连接的炉灶获得工作台倍率；不必为了仅提升该工作台上的速度而改 Pawn 的 `CookSpeed`。先核对具体配方是否改用了其他属性、实际工序是否走这条路径。参照 `Buildings_Misc.xml → ToolCabinet`、`Buildings_Production.xml → BenchBase / TableSculpting`、`Recipes_Meals.xml → CookMealSimple`。对照同 Pawn/配方的实际完成时间，切换设施供电或移除后复查。

## 种植建筑与装饰花盆

- `RimWorld.WorkGiver_Grower.PotentialWorkCellsGlobal` 会枚举 `RimWorld.Building_PlantGrower`；但 `RimWorld.WorkGiver_Grower.CalculateWantedPlantDef` 经 `Verse.GridsUtility.GetPlantToGrowSettable` 先查格子上的主体建筑（edifice），再查种植区。`RimWorld.FertilityGrid.FertilityAt` 也仅从主体建筑读取建筑肥力，否则回到地形路径。故叠放的非主体花盆即使换成种植器类、填写肥力，也不会据此成为该格子的原版种植目标或肥力来源。
- 真种植参照 `Buildings_Production.xml → HydroponicsBasin`（`thingClass`、`fertility`、`building/defaultPlantToGrow`、`building/sowTag`）。仅装饰用贴图；同时要叠放与真实种植时，单独设计宿主、播种与生长链，不假设 XML 换类足够。验收选作物、播种、生长、收获及读档；生长慢则从 `RimWorld.Plant.GrowthRate` 检查肥力、光照和温度等因子。

## 工单可选与可执行

- `Verse.ThingDef.AllRecipes` 合并工作台的 `recipes` 与 `RecipeDef.recipeUsers`；列得出工单不等于接得了任务。`RimWorld.WorkGiver_DoBill.JobOnThing(Pawn,Thing,bool)` 的候选检查走 `RimWorld.IBillGiver.UsableForBillsAfterFueling`，而 `Verse.AI.JobDriver_DoBill.MakeNewToils` 通过 `CurrentlyUsableForBills` 检查执行阶段。原版 `RimWorld.Building_WorkTable` 的前者检查供电/故障，后者还检查当下燃料；仅修改后者不等于改变派工门槛。
- 参照 `Buildings_Production.xml → ElectricStove / FueledStove`。分别复现工单列出、缺料/断电/缺燃料时的派工、补给后恢复和正常产出，优先定位出错的阶段。

## 邻座娱乐

- `RimWorld.JoyGiver_InteractBuilding.CanInteractWith`（父类）筛掉未通电的 `CompPowerTrader` 建筑；`RimWorld.JoyGiver_InteractBuildingSitAdjacent.TryGivePlayJob` 找可预留的相邻座位，并按 `requireChair` 决定能否退到无椅格。开始后的任务由 driver 负责；`RimWorld.JobDriver_SitFacingBuilding.MakeNewToils` 将建筑传给 `RimWorld.JoyUtility.JoyTickCheckEnd`，后者据 `JoyGainFactor` 与 JobDef 的 `joyGainRate` 计算娱乐增量。只在 giver 加检查不保证运行中断电会停止；自定义 driver 未传来源时不能假设建筑倍率已应用。
- 参照 `Buildings_Joy.xml → ChessTable`、`JoyGivers.xml → Play_Chess` 与 `Jobs_Joy.xml → Play_Chess` 的连接。测试座位有/无、供电前后派工、中途断电、娱乐增长和停止条件。

### 原版 XML 证据（游戏根目录相对路径、SHA256）

| 文件 | SHA256 |
| --- | --- |
| `Data/Core/Defs/ThingDefs_Buildings/Buildings_Furniture.xml` | `cea362ca9451f0762f8a104b2344bd540b5f6e8663dd9a4e75f3c39b46607c55` |
| `Data/Core/Defs/ThingDefs_Buildings/Buildings_Misc.xml` | `3ee922aa81ded536f0a1e887ae49e7755f0d0deb07a1337c9baf03fca8e4247a` |
| `Data/Core/Defs/ThingDefs_Buildings/Buildings_Production.xml` | `3221c30adc223498636ac7b6ca86ef9c50fce681b138be8f0919c6e652045a31` |
| `Data/Core/Defs/RecipeDefs/Recipes_Meals.xml` | `ecb025e0b521b2e174f3d8cecb7d0263a1c7310b957cf6d849d414361b566789` |
| `Data/Core/Defs/ThingDefs_Buildings/Buildings_Joy.xml` | `65ed52b04b95c1c60eacde4490689b22644ba66855d78d0a6a1384934e3cb35c` |
| `Data/Core/Defs/Joy/JoyGivers.xml` | `e35331b3cd709de271871bdf75400c7bb45ad7181dcad30ba8b9efc0dca1439f` |
| `Data/Core/Defs/JobDefs/Jobs_Joy.xml` | `20fdcac408eef887747be30416a47155d4c9509193dd35af4496bb3b59e2d056` |
