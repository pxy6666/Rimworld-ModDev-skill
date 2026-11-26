# Apparel 对位合同

Apparel、穿戴图、身体覆盖层、头饰/发型配套，以及任何依赖 pawn 身型锚点的素材必须使用本合同。普通独立图标或建筑贴图不套用此流程。

## 1. 确认真实消费者

由 `rimworld-mod` 提供或以只读方式从目标版本工程和上游实现取证。对每个支持的消费者记录：

- 实际 Apparel Def、继承关系、`wornGraphicPath` 或框架等价字段；
- graphic class、body type、sex、age、race 变体；
- 所需 direction set、文件后缀和状态变体；
- `drawSize`、实际 load root/`LoadFolders` 映射；
- `wornGraphicData` 中按 direction、body type 或二者组合选择的 offset 与 scale；
- `renderUtilityAsPack`，以及 Pack/Belt 路径实际采用的定位、缩放、旋转、镜像和遮挡行为；
- body type 的 `headOffset`，以及 Overhead、EyeCover、头饰等消费者实际匹配的 head/head type；
- apparel layer、相邻外衣关系，以及相关 render node/worker 在各方向施加的 draw offset、scale 或其他 placement transform；
- shader，以及会影响位置、尺寸和前后遮挡的目标 renderer 行为。

每项 placement transform 都要记录目标版本中的字段值、适用条件和代码/Def/运行截图证据。消费者、方向、变体或变换未知时，不从常见命名、另一版本或零偏移假设推断。

## 2. 获取匹配的 body baseline

为**每个受支持消费者**定位版本匹配、体型匹配、方向匹配的 vanilla 或 upstream body texture。基准必须保留原始 canvas、像素坐标、origin 和真实透明背景，并记录来源、版本、文件哈希与使用条件。

Overhead、EyeCover 和其他 headgear-like 消费者还必须定位匹配的 head/head type baseline。预览时，该 head baseline 必须按实际 body type 的 `headOffset` 和相关 render-node draw offset 放到 renderer 使用的位置；不能只用 body baseline，也不能把头部固定在身体画布的零偏移 origin。

仅供对位的 body、head 与其他 baseline 文件不得进入游戏加载或发行内容根，包括任何 `Textures`、`Common`、版本目录、`LoadFolders` 自定义内容根和发行暂存目录。优先就地只读访问已安装资源；需在项目中暂存时用 `.local/art-references/`，不得把该目录或其链接列为内容根。运行时复用应记录合法依赖和引用，不能把“可读取作参考”当作“可重新分发”。

按 reference-only 单列每份基准的源路径、本地路径（如有）和实际文件的 SHA-256，连同来源与使用条件保存在包外；交接时将清单交给 [发行包检查](../../rimworld-release/references/package.md)。如果最终发行文件清单中命中任一参考路径**或** SHA-256（即使文件改名或换目录），必须停止发行并清理、重打包、复核；不能只以 `.local/` 排除规则代替最终检查。

## 3. 建立 one-canvas composite

每个 body/sex/type/direction 组合建立固定画布模板，至少包含：

1. 不可重绘的 body baseline layer；
2. headgear-like 消费者所需的匹配 head baseline layer；
3. 独立、透明的 apparel work layer；
4. 固定 canvas 边界、origin、方向和变体标识；
5. 肩、腰、手臂、腿、脚和头部等对位锚点；
6. 独立的 renderer-preview 配置，逐项记录将对 baseline 与 apparel 应用的已验证 placement transforms。

Apparel work layer 与正式导出文件始终使用同一 canvas、origin 和像素坐标系。Renderer preview 可以在合成时应用已验证的 draw-time offset、scale 和其他 placement transform，但不得把这些预览变换烘焙进 apparel work layer。多体型或多方向分别使用匹配模板，不能把一个模板缩放后冒充其他消费者。

## 4. 在模板内生成、编辑或核验已供素材

图像工具必须看到对应 body baseline 和 apparel 可编辑区域，并明确：

- 只生成或修改 apparel，不重画身体；
- 不改变 canvas、origin、方向、锚点或透明区；
- 不加入棋盘格、纯色背景、文字、额外角色或身体部位；
- 风格参考只能改变服装外观，不能移动身体基准。

若输出把 body、背景和服装合成成不可分离像素，必须重新编辑、重做或停止，不能直接作为 worn graphic。

用户或工程已提供穿戴图时不要求重新生成；在对应模板中以原文件作为独立 apparel 层核验，仍执行下文的正式文件检查和逐方向合成。不能因文件来源或直接复用而跳过对位。

## 5. 导出 apparel layer

正式文件只导出 apparel layer，并保持模板完全相同的：

- canvas 尺寸和 origin；
- direction 与消费者映射；
- 透明区及真实 alpha；
- 项目要求的 binary alpha 或 soft alpha convention。

禁止自动 `trim`、`crop`、`recenter`、旋转或单方面 `resize`/缩放。任何经明确需求批准、会改动源模板或正式 PNG 的尺寸变换都必须对 body 与 apparel 采用同一变换，并重新完成全部合成检查；不能用后处理“修正”未知锚点。

Renderer 在 draw time 使用的 offset、scale、Pack/Belt 或 head placement transform 只属于预览与 renderer 证据，不是裁剪、移动、缩放或改写正式 apparel PNG 的许可。正式 PNG 仍必须保持同 canvas、origin、direction 和 alpha。

## 6. 为每个变体生成完整预览

使用**正式导出的同一 apparel 文件**，为每个受支持的 body/sex/type/direction 生成 renderer-accurate body-plus-apparel composite，不得用另一份预览专用图替代。每张预览必须：

1. 使用该消费者匹配的 body baseline；
2. 对 Overhead、EyeCover 和其他 headgear-like 消费者加入匹配的 head/head type baseline，并应用实际 body-type `headOffset`；
3. 按目标 renderer 的真实顺序应用该方向、body type 和消费者的 `wornGraphicData` offset/scale、`renderUtilityAsPack`、Pack/Belt 行为及相关 render-node draw offsets；
4. 保存所用字段值、计算结果和证据，使预览变换可复算；
5. 仅在所有必需变换均已验证且准确应用后才进入视觉检查。

直接把 body 与 apparel 在一个 origin 上逐像素叠加，不能证明游戏内对位。只有目标 renderer 证据明确显示该消费者的全部 placement transforms 都是零偏移、单位缩放且无额外节点变换时，零变换合成才可作为通过证据。完成准确变换后逐项检查：

- 肩线、腰线、手臂、腿部和脚部对位；
- 头饰相对匹配 head baseline、脸部和发型的对位；
- East/West 等侧面朝向、镜像和左右锚点；
- South/North 的身体前后关系与 apparel 前后排序；
- 与内层/外层 outerwear 的交互；
- Pack/Belt mode 经实际 offset/scale 后的位置和遮挡；
- 透明边缘、留白及游戏小尺寸 readability。

任一受支持变体失败，整组不得标为对位通过。

## 7. 保存明确的 layer/order 证据

每个相关方向都要记录目标 renderer 中的明确证据：消费者使用的层/模式、身体与 apparel 的前后顺序、相邻 outerwear 或 Pack/Belt 的顺序、body/head/apparel 的最终 offset 与 scale，以及对应的变换后合成图或游戏截图。像素位置不能替代 render layer 证据；South/North 顺序也不能仅凭 apparel 单图推断。未应用准确 placement transforms 的零偏移合成不能作为 renderer 证据。

## 8. 停止与交接

出现以下任一情况即停止正式批量或完成声明：

- 没有匹配版本、body、方向或消费者的 baseline；
- body 与 apparel 没有可分离图层；
- 工具无法稳定保留 canvas、origin 或 alpha；
- 任一必需的 `wornGraphicData` direction/body-type offset 或 scale 未知；
- `renderUtilityAsPack`、Pack/Belt 定位行为或相关 render-node draw offset 未知；
- headgear-like 消费者缺少匹配 head/head type baseline，或 body-type `headOffset` 未知；
- 无法确认预览已按目标 renderer 的顺序准确应用全部 placement transforms；
- 任一变体合成对位失败；
- render layer/order 未知或没有目标 renderer 证据；
- body baseline 的来源或使用条件不明。

通过后，将正式文件、消费者映射、路径、哈希、模板/合成预览、layer/order 证据和包外 reference-only 清单交回 `rimworld-mod` 绑定与后续发行核验；只绑定正式素材，不绑定对位基准。绑定后仍出现错位或遮挡错误时交给 `rimworld-debug`，不得只重复生图。

仅 PNG 可打开、仅尺寸相同或仅 apparel 单图看起来正确，都不构成对位通过。
