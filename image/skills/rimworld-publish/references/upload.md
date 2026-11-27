# 上传与恢复

## 离线准备

`--content` 指发行包内 **`About/About.xml` 位于根下的那一个 Mod 目录**。用同一发行目录中与它同级的 `release-receipt.json` 和 `manifest.json` 核对目录和每个文件的 SHA-256。不要移动或手改 staging 来绕过校验；内容变化时重新打包和计划。

包收据只证明打包时的静态检查。另核对这份内容哈希在用户约定范围内的加载、玩法等验收证据；未完成的项目必须已获用户明确接受才作为例外纳入发布。`--acceptance <说明>` 必填，记录验收范围、证据引用或接受的例外，随该包哈希保存。验收通过或接受例外不等于授权上传。

在当前启用技能目录定位 `scripts/publish.py`，按 `--help` 核对所用版本的命令。Windows PowerShell 示例：

```powershell
# 现有物品；已有受核验的 About/PublishedFileId.txt 时可由计划解析目标。
python -X utf8 <技能目录>/scripts/publish.py plan --content <已核验Mod目录> --item-id <已确认ID> --journal <本地记录.json> --acceptance '<验收范围与证据或已接受例外>'
# 新建；标题、主图明确选定，未指定可见性时采用私密。
python -X utf8 <技能目录>/scripts/publish.py plan --content <已核验Mod目录> --create --title <标题> --preview <主图路径> --journal <新本地记录.json> --acceptance '<验收范围与证据或已接受例外>'
```

不确定目标时先核对现有物品 ID 与包标记；不能把 ID 缺失、失效或无权限当作创建授权。可加 `--project <工程根>` 核对项目身份。`plan` 即离线预览，保存包身份、内容校验、明确物品和写入范围，不连接 Steam，也不上传。journal 放在本地、上传内容根之外。

## 页面写入范围

更新总是提交已核验的 Mod 内容。以下输入仅在用户选择时纳入计划，未选择的既有页面字段保持原样。

| 变更 | 计划参数与边界 |
| --- | --- |
| 标题、描述、语言 | `--title`、`--description-file`；只有显式改标题/描述时才写对应语言槽，`--language` 可指定主槽，省略时用 Steam 默认槽 |
| 主图与可见性 | `--preview`、`--visibility public\|friends-only\|private\|unlisted`；现有物品省略则保留，新物品需选主图、标题且默认私密 |
| 本次变更说明 | `--changelog`；仅用于本次提交，不代替页面描述 |
| 其它语言槽 | 重复 `--locale LANGUAGE=FILE`；每个文件为 UTF-8 JSON，只能含 `title` 和/或 `description`；未声明的语言和字段保留 |
| 图片库 | `--replace-screenshots <图片路径 ...>` 明确替换图片；只写标记、不带路径明确清空图片。保留不属图片的预览内容；未指定不触碰图片库 |
| 描述里的前置说明 | `--append-requirements` 读取已核验包的 `About.xml`，只追加到本次明确选中且提供文本的描述槽。必需依赖和加载顺序分别显示 |
| 工坊必需项目和 DLC | `--add-dependencies` 单独选择。只添加已知 ID 且尚未登记的必需依赖，保留已有条目。单纯的 `loadAfter` 只用于说明 |

附加前置说明和写入工坊依赖可独立选择。依赖取发行包支持版本所用声明的并集，优先使用 `About.xml` 的工坊链接，缺链接时以本机已安装工坊内容的包 ID 匹配。审阅计划中的依赖来源和 ID，尤其是只在某个版本需要的依赖，因为工坊展示适用于整个条目。无法明确解析的必需依赖列入 `unresolvedRequired`，需人工核对。状态里的 `complete` 表示已排入的步骤都完成，`dependenciesComplete` 另报告显式选择的依赖项是否都已核实。

计划要明确区分主图与附加截图。替换、清空和公开均依据用户选择。已选图片达到 1 MB 时，离线计划用 Pillow 压缩副本，原图留在原处。主图副本采用 PNG 且两边至少 512 px。审阅压缩结果，保留 journal 同目录内记录的压缩副本，上传前会校验它的哈希。没有 Pillow 时可安装 Pillow 或提供更小的图片。

替换图库期间请停止在其它客户端编辑同一物品的预览。Steam 按位置移除预览；工具会在提交前重新核对图库，有变化就停止。

## 执行和结果

上传前核对用户已授权的目标、包哈希、页面变更以及当前 Steam 会话；按 [SDK 环境](sdk-env.md) 执行：

```powershell
python -X utf8 <技能目录>/scripts/publish.py upload --journal <本地记录.json>
python -X utf8 <技能目录>/scripts/publish.py status --journal <本地记录.json>
python -X utf8 <技能目录>/scripts/publish.py inspect --item-id <工坊ID> --language schinese --language english
```

`inspect` 通过当前 Steam 会话只读查询页面与工坊依赖。语言内容以 Steam 返回为准，Steam 可能回退到默认语言。依赖查询缺少接口或结果不完整时，报告查询错误。

首次创建并完成上传后，用户同意保存标记时运行 `bind --journal <本地记录.json> --project <源工程根>`。它将新 ID 写入源工程的 `About/PublishedFileId.txt`，核对包身份并保护已有绑定。后续发布前重新打包。Steam 提示须接受工坊协议时，请用户在 Steam 处理并核对可见性。转公开是独立选择。

保留同一个 journal，逐步报告状态。工坊依赖写入后会回读核对。确认缺失的项可随同一 journal 续传，续传先查当前已有依赖。写入后回读失败，或写入回执有歧义时按结果未知处理。

| 状态 | 下一步 |
| --- | --- |
| 已知失败 | 查明并纠正原因；目标和授权范围未变时，以原 journal 执行 `upload` 续未完成步骤。若改变了输入，重计划并保留旧记录 |
| 已完成 | 用返回的实际 ID 交付工坊链接和已应用操作；必要时核对实际页面。上传完成不证明游戏内可用 |
| 结果未知（包括提交后连接断开、等待回执超时） | 停止自动重试，不另开 journal 规避。从 Steam 客户端、该物品的实际状态或可信回执核实该步结果。Windows 可按物品 ID 和时间核查 Steam 安装目录内的 `logs/workshop_log.txt`；只有日志明确确认在提交生效前失败才可标为失败 |

只有掌握可信证据后才按实际结果 `resolve --journal <记录.json> --outcome completed|failed --evidence <证据说明>`；已知创建成功还要传 `--item-id <已核实的新ID>`。`failed` 只在确认该步未生效时使用。没有结论就保留未知并交代如何进一步核实。
