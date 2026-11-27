# 事件发放与任务信号

写任务、事件或地图目标的任务联动时读取。叙事结构和切换见 [任务与地图入口](quest-chain.md)，持久状态见 [状态与存档](quest-state.md)。按 [版本查证](local-lookup.md) 查实际 XML 与方法，按 [玩家可见文本](player-facing-text.md) 校对信件、目标与失败提示。

## 确定发放者和目标

- **开局。** 用实际 `Scenario` / `ScenPart` 核对初始地点、抵达方式、物件或 Pawn 创建的时机。绑定对象后进入共同的任务发放路径。已有存档的中途入口单独说明。
- **叙事者或显式事件。** `IncidentDef` 指定执行器和目标。`IncidentWorker_GiveQuest` 依次取事件指定的脚本、`IncidentParms` 指定的脚本或随机选择器。定向事件可只在规定入口调用。常规事件还受 `CanFireNow` 和叙事者选择条件影响。
- **对象互动或上一阶段。** 物品、建筑、任务零件或组件可发信号或直接发放任务。Odyssey 检查引擎既向引导任务发送 `.Inspected`，也独立生成父任务。多个入口共享进度时统一检查已经生成、旧档已处于哪一阶段、该目标是否仍然可用。按设计判断可否重发。
- **任务再触发事件。** `QuestPart_Incident` 可以在收到信号后尝试执行一个事件。明确目标地图、资格、失去地图时的回退与失败处理，核对目标版本 worker 是否会重定向。

## XML 与调度速查

| 要核对什么 | 对应 Def 或组件字段 |
| --- | --- |
| 事件类型、目标和执行方式 | `IncidentDef.workerClass`、`category`、`targetTags`、`questScriptDef`。按 worker 核对目标地图、世界或商队，按场景核对 `allowedBiomes`、`disallowedBiomes`。 |
| 事件何时可选 | `baseChance`、`baseChanceWithRoyalty`、`earliestDay`、`minRefireDays`，按需核对人口、难度、殖民者在场和威胁点数字段。权重、重发间隔与剧情进度是不同条件。 |
| 谁调度事件 | 在目标 `StorytellerDef` 或组件中查实际启用条件、目标和并行限制。`SingleOnceFixed` 用于一次性时间入口，`OnOffCycle` 是周期安排，`RandomMain` / `CategoryMTB` 是随机调度，`RefiringUniqueQuest` 是独特任务的重发候选。 |
| 任务进入候选池 | `QuestScriptDef.rootSelectionWeight`、点数曲线、`randomlySelectable`、`isRootSpecial`，按需查 `rootEarliestDay`、`rootMinPoints`、`rootMinProgressScore`、`minRefireDays`。`isRootSpecial` 的任务可由显式入口发放，实际候选规则看选择器。 |
| 任务界面和生命周期 | `root` 决定装配，`autoAccept`、`expireDaysRange` 和 `sendAvailableLetter` 影响接取流程。按需检查 `everAcceptableInSpace`、`neverPossibleInSpace`、`endOnColonyMove`、`defaultHidden` 和 `hideOnCleanup`。任务显示由 `questNameRules`、`questDescriptionRules` 等控制。节点专属条件按 `Class` 查证。 |

原版 `GiveQuest_Random` 与 `GiveQuest_EndGame_ShipEscape` 共用事件基类。后者配置指定脚本，`baseChance` 为 0，由叙事者的专门入口发放。定位 `Core/Defs/Storyteller/Incidents_World_Quests.xml` 和 `Storytellers.xml`。单个作品中的权重、间隔、天数和点数仅用于理解它的实现，填写项目值沿用现有制作模式。

## 验证信号如何推进

`QuestNode_Sequence` 在任务生成时装配 `QuestPart`。运行时由信号、计时和监听阶段决定动作。`QuestNode_Delay` 的 `outSignalComplete` 可续接后续步骤。查 `QuestGenUtility.HardcodedSignalWithQuestID` 与 `Quest.Notify_SignalReceived`，核对信号会加在哪个任务实例上、何时有监听，以及实际对象的 `questTags` 何时绑定。处理 `SUBJECT` 等参数时确认对象身份，尤其是多个同类任务或同一张地图上有多个目标时。

沿用同一份 [任务与地图交接记录](feature.md#任务与地图交接)。按本次情节区分抵达、地图生成、互动、带走与交付。任务结算与界面按实际选定的条件推进；涉及重叠信号或中途存读档时查 [状态边界](quest-state.md#状态边界与去重)。

原版案例来自已查证的 1.7.5014 rev1195 发行文件及程序集。其他构建和上游项目按实际文件复核。

- **Core 强盗营地**在 `site.MapGenerated` 后停掉未访问倒计时，`site.Destroyed` 判失败，`site.AllEnemiesDefeated` 判成功并发放奖励。定位 `Core/Defs/QuestScriptDefs/Script_BanditCamp.xml` 与 `Core/Defs/Sites/Parts/BanditCamp.xml`。
- **Core 倒地难民与袭击**分别展示 `QuestNode_WorldObjectTimeout` 和使用 `QuestNode_SubScript` 调用 `Util_Raid`。定位 `Core/Defs/QuestScriptDefs/Script_DownedRefugee.xml` 与 `Scripts_Utility_ThreatsCore.xml`。
- **Odyssey 机械中继站与储藏库**的判据不同。前者聚合指定稳定器的骇入或销毁结果，后者在地表地图生成时判成功，地下核心拾取属于后续行动。定位 `Odyssey/Defs/QuestScriptDefs/Script_GravShip.xml`、`Odyssey/Defs/Sites/GravcoreLocations.xml` 及对应任务根节点。
- **派系扩展样本**可用本地 Milira Imperium（`Ariandel.MiliraImperium`，工坊 `3588393755`）的 `Incidents_Milira_Imperium.xml` 与 `Milira_ImperiumIntro` 作定向发放对照。该例有自定义 worker，使用前另查对应加载版本和入口。
