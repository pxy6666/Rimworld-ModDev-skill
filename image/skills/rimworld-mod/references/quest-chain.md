# 任务、事件与预设地图

制作或修改任务、叙事者事件、分章目标、任务地点上的预设建筑时读取。排错遇到任务链永久停住时也读。这是设计约束，不代替目标版本的原始 XML。

证据：RimWorld 1.7 当前安装与 1.6.4871 备份。任务和事件两边结构一致，见 `Data/Core/Defs/Storyteller/Incidents_World_Quests.xml`、`Storytellers.xml`、`Script_TradeRequest.xml`、`Script_DownedRefugee.xml`、`Scripts_Utility_ThreatsCore.xml`。预设地图见 `Data/Core/Defs/MapGeneration/CommonMapGenerator.xml`、`Sites/Parts/BanditCamp.xml`，以及奥德赛 `PrefabDefs`、`LayoutDefs/Layouts_Mechhive.xml`、`Sites/Opportunities.xml`、`TileMutators/TileMutators_AncientStructures.xml`、`MapGeneration/MechhiveMapGenerator.xml`。1.6 备份的 `Data/Odyssey/Defs/PrefabDefs` 同样有预制体。节点和生成步骤的 C# 没有逐方法反编译。

## 事件和任务怎么接上

叙事者组件决定什么时候点名一个 `IncidentDef`。事件决定这次发生什么。这次若是发任务，再由 `QuestScriptDef` 生成那一份任务。

随机任务走类别 `GiveQuest`、执行类 `IncidentWorker_GiveQuest`。`GiveQuest_Random` 不写 `questScriptDef`，`earliestDay` 为 2，在 `rootSelectionWeight` 大于 0 且当前能生成的脚本里抽。写了 `questScriptDef` 的事件只发那一份，`baseChance` 经常是 0，不会被随机抽到。飞船结局由 `StorytellerCompProperties_SingleOnceFixed` 在第 20 天后点名 `GiveQuest_EndGame_ShipEscape`。

`QuestScriptDef` 的 `root` 多半是 `QuestNode_Sequence`。序列只决定生成时登记零件的顺序。运行后下一步靠 `inSignal` 叫醒，不按 XML 从上往下自动执行。`QuestNode_Delay` 用 `outSignalComplete` 交出自己的信号。倒地难民用 `QuestNode_WorldObjectTimeout`（`isQuestTimeout`）和地点消失结束任务。袭击通常不直接填一个随机 `IncidentDef`，而是 `QuestNode_SubScript` 调用 `Util_Raid` 里的 `QuestNode_Raid`。

跨任务的衔接有三种：同一份任务里的多个信号；`QuestNode_SubScript` 复用另一份脚本；父任务根节点上的 `subquestDefs`（奥德赛引力引擎）或隐藏父任务再拆轮次。下一章若只由上一份任务的某一个信号发出，那个信号丢失后链就断了。

### 事件上会改变是否发生的字段

| 字段 | 作用 |
| --- | --- |
| `workerClass` | 谁执行。发任务用 `IncidentWorker_GiveQuest` |
| `category` | 叙事者按哪一类抽。`Misc`、`ThreatBig`、`GiveQuest`、`OrbitalVisitor` 不是同一口池子 |
| `targetTags` | 发生在哪里。`Map_PlayerHome` 是玩家殖民地，`World` 是世界 |
| `baseChance` | 该类别内的权重。0 表示不进随机 |
| `baseChanceWithRoyalty` | 有皇权时的权重 |
| `earliestDay` | 最早第几天 |
| `minRefireDays` | 再次发生至少隔几天 |
| `minPopulation`、`minGreatestPopulation`、`minDifficulty` | 人口和难度门槛 |
| `requireColonistsPresent` | 地图上必须有殖民者 |
| `minThreatPoints`、`maxThreatPoints`、`pointsScaleable` | 威胁点数 |
| `questScriptDef` | 写了就只发这一份任务 |
| `letterLabel`、`letterText`、`letterDef` | 不发任务、直接发信时的信 |
| `pawnKind`、`pawnFixedGender`、`pawnMustBeCapableOfViolence`、`pawnHediff` | 事件直接生成一个人 |
| `allowedBiomes`、`disallowedBiomes` | 生物群系 |
| `populationEffect` | 对人口意图的影响 |
| `hidden` | 不出现在普通列表 |

帝国（`Ariandel.MiliraImperium`，工坊 3588393755）的 1.7 `Incidents_Milira_Imperium.xml` 用的是同一套字段，执行类是它自己的 `IncidentWorker_GiveMiliraImperiumQuest`。初次接触和坠鸡 `baseChance` 0、`minRefireDays` 99999。观光团权重 1、至少隔 60 天。海盗藏身处权重 1、至少隔 25 天。皇权访客权重 1、至少隔 40 天。结局要求 `requireColonistsPresent`。这些数字只说明那份文件，不要抄成新任务的默认值。

### 任务脚本上会改变是否抽到、何时结束的字段

| 字段 | 作用 |
| --- | --- |
| `root` | 节点树。每个节点自己的字段才是这一步的参数 |
| `rootSelectionWeight` | 被 `GiveQuest_Random` 抽中的权重。不大于 0 就不会被随机抽到 |
| `rootSelectionWeightFactorFromPointsCurve` | 威胁点数怎样改这个权重 |
| `isRootSpecial` | 离开随机池，只能由点名它的事件发放 |
| `randomlySelectable` | 是否允许进随机 |
| `rootEarliestDay`、`rootMinPoints`、`rootMinProgressScore` | 天数、威胁点数、进度分门槛 |
| `minRefireDays` | 同一脚本再次发放的间隔 |
| `expireDaysRange` | 不接受就过期，写成 `4~8` |
| `defaultChallengeRating` | 任务星级 |
| `autoAccept`、`sendAvailableLetter` | 跳过接受界面，或仍发「有任务可接」的信 |
| `questNameRules`、`questDescriptionRules`、`questContentRules` | 标题、正文、内部文本的规则 |
| `everAcceptableInSpace`、`neverPossibleInSpace` | 轨道地图能不能发 |
| `endOnColonyMove` | 殖民地搬走时结束 |
| `defaultHidden`、`hideOnCleanup` | 隐藏或结束后不留在列表 |

帝国初次接触脚本 `Milira_ImperiumIntro` 写了 `isRootSpecial`，`rootSelectionWeight` 被注释掉，`expireDaysRange` 是 3~5。它不会从随机池冒出来。

贸易请求的定居点距离是节点字段 `maxTileDistance` 32，不是 `QuestScriptDef` 的通用字段。节点参数以那一个 `Class` 的原始 XML 为准。

### 叙事者组件决定频率

组件不写在单个事件里。

- `StorytellerCompProperties_OnOffCycle`：点名一个 `incident`，`onDays`、`offDays`、`minSpacingDays`、`numIncidentsRange`、`minDaysPassed`。
- `StorytellerCompProperties_RandomMain`：`mtbDays` 是平均间隔天数，`categoryWeights` 决定各大类比重。
- `StorytellerCompProperties_CategoryMTB`：某一类自己的 `mtbDays`。
- `StorytellerCompProperties_SingleOnceFixed`：`fireAfterDaysPassed` 之后点名一次。
- `StorytellerCompProperties_RefiringUniqueQuest`：独特任务按条件再发。皇家飞升 `minDaysPassed` 35、`refireEveryDays` 22。这是那种阶段的间隔，不是所有剧情的默认值。
- `allowedTargetTags` 限制发生地点。`enableIfAnyModActive` 在缺少对应模组时不启用该组件。

随机任务由发放 `GiveQuest` 的组件周期点名，不由任务脚本自己计时。

## 长剧情

拆成多章短任务。每一章自己结束。进度记在任务外面。下一章由叙事者按这个进度再发。不要把整条故事写成一份一直挂着的任务。

正在等待的节点不会重放已经错过的信号。能恢复的是「故事进行到第几章」，不是那一份已经卡住的任务。

每一章单独一个 `QuestScriptDef`，再配一个只发这一章的 `IncidentDef`。事件写上 `questScriptDef`，`baseChance` 设为 0。脚本加上 `isRootSpecial`。进度放在会存档的世界组件里，记完成到第几章。本章成功时才把章号加一。超时、目标消失、关键人物死亡只结束这一章，不把前面的章号清掉。

下一章由叙事者组件按章号发放。发放前确认这一章还没完成，并且没有同名任务正在进行。过几天再问一次用 `OnOffCycle`。只该出现一次的开场用 `SingleOnceFixed`。需要隔一段时间再出现的阶段用 `RefiringUniqueQuest`。

同一章内部的步骤用 `inSignal` 串联。完成条件准备两条发出途径：任务节点自己发信号；地图或世界组件发现目标已经达成时，再补发同一个信号。补发只表示完成，不把失败改成成功。

每一章至少两条出路。成功是一条。另一条必须在成功信号永远不来时结束本章：天数到期、`QuestNode_NoWorldObject` 一类的目标消失、关键角色死亡，或派系转成敌对。贸易请求用派系变敌对来失败。失败信要写明这一章结束了，以及故事停在哪一章。不要用一组必须同时成立、又没有总期限的条件当作唯一出口。

不要把十几章的等待和分支塞进同一个 `Quest`。不要只在上一章的成功信号里生成下一章。不要把唯一进度只放在任务零件里。`minRefireDays` 设得很大只能减少重复发放，不能代替章号判断。随机池里的任务结束后仍可能被 `GiveQuest_Random` 再抽到。

旧存档里已经接取、又没有第二条出路的任务，后改的脚本叫不醒它。要兼容这些存档，读档时把超时未完成的同名任务结束掉，章号停在上一章，并在记录里写明影响哪些存档。

超时天数按这一章实际在等什么来定。原版贸易请求的可接受期限是 4～8 天，倒地难民的地点超时大约 7～15 天。不把这些数字当成每一章的统一默认值，也不覆盖已经写明的期限。

## 预设地图

预设地图不是一份可以放进模组的存档。玩家进入时，游戏按 `MapGeneratorDef` 的 `genSteps` 生成地形，再由其中的步骤把设计好的建筑放上去。

`CommonMapGenerator.xml` 里的顺序：10～100 是高度和肥沃度，200～300 是自然地形，400～500 是任务地点和据点这类关键建筑，700～800 是废墟等非关键建筑并且必须避开已经被占用的格子，850 是玩家落点，900～1200 是间歇泉、植物和动物，1500 是战争迷雾。关键建筑放在 400～500。放得太晚会被岩石或植物盖住，放得太早又没有地形可站。

整张特殊地图用自己的 `MapGeneratorDef`，父类用 `MapCommonBase` 或轨道地图的 `SpaceMapGenerator`，只追加需要的步骤。`WorldObjectDef.mapGenerator` 或剧本里的 `mapGenerator` 指向它。机械巢穴的世界物体用 `Mechhive`，生成器在 290 放主体、900 以后才撒残骸。只做一处任务地点时，不要替换玩家主地图的生成器。

地面任务地点用 `SitePartDef` 加同名的 `GenStepDef`。`linkWithSite` 写成地点部件的 defName，这样只有这个地点会跑这些步骤。土匪营地的步骤是 `GenStep_Outpost`，`order` 400，下一步供电是 401。`SitePartDef.minMapSize` 必须装得下要放的建筑。地点没生成出来时，对应任务章要有第二条出路，不能干等一个永远不会出现的地图物体。

画好的一块建筑优先用数据，不要先写整张地图的生成器：

- `PrefabDef` 是一块固定尺寸的物件和地板。常用字段是 `size`、`rotations`、`things` 里的 `position` 或 `rects`、`stuff`、`chance`，以及 `terrain` 的矩形。预制体里还可以再嵌一块预制体。不写死 `chance` 和旋转时，每次生成会不一样。
- `StructureLayoutDef` 是一组房间。`roomDefs` 里的数字是权重或 `countRange`，`workerClass` 负责把房间排进布局，另有门、外墙和周围地板。机械巢穴的主体是这种布局，不是一张画死的平面图。
- `SketchResolverDef` 用 C# 生成草图。类必须按目标游戏版本编译。帝国引力船开局曾在 1.7 上因为 1.6 的 `SketchResolver_Prefab` 空引用而失败，自定义解析器要单独核对。
- 轨道地点的 `GenStep_OrbitalPlatform` 接收 `layoutDef` 和 `exteriorPrefabs`。世界格上的古代驻军用 `TileMutatorDef`，`workerClass` 为 `TileMutatorWorker_AncientStructure`，`structureLayoutDef` 决定主体，`scatteredPrefabs` 决定四周零散件。
- `GenStep_ScatterGroupPrefabs` 按 `countPer10kCellsRange` 和 `minSpacing` 撒多块预制体，适合残骸，不适合「这一章的唯一建筑必须出现在这里」。

没有奥德赛时不要依赖 `PrefabDef` 和 `StructureLayoutDef`，它们在奥德赛数据里。1.6 与 1.7 的核心地点步骤仍然是 `SitePartDef` 加 `linkWithSite`。

## 制作时要写入功能记录

- 章节标记的存档字段、谁写入、谁读取、失败时是否保留。
- 每一章的成功信号、第二条出路、超时长度和结束后玩家看到的信。
- 下一章的发放者，以及「当前没有同名任务」的判断。
- 预设地图用的是整张 `MapGeneratorDef`、地点 `GenStepDef`，还是预制体、布局或草图。地图尺寸、步骤 `order`、哪些格子必须空出来。
- 证据版本：用到的定义来自 1.6 还是 1.7 的哪一份原始 XML。
- 未验证项：没进游戏触发过的信号、重发、读档迁移和地图生成不要写成已通过。
